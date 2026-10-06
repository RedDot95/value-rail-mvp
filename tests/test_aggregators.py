"""Offline tests for the discovery-only aggregator connectors (CoinGate MCP, BuySellVouchers, CardBear,
GiftCardWiki) against recorded, dated, personal-data-free fixtures from 06.10.2026."""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from value_rail.connectors.aggregators import (AGGREGATOR_KINDS, BsvListConfig, BsvPage, CardBearPage,
                                               CoinGateBrand, CoinGateSearch, _mcp_decode, build_aggregator,
                                               face_from_title, parse_bsv_list, parse_cardbear,
                                               parse_coingate_gift_card, parse_coingate_search, parse_gcw_hotdeals)
from value_rail.domain.enums import RouteStatus, SourceKind, SourceRole
from value_rail.net.errors import (AccessDenied, ParserBroken, RateLimited, RobotsDisallowed, UnexpectedEmpty,
                                   UpstreamError)
from value_rail.net.http_safe import TransportResponse
from value_rail.worker.scan import run_scan

from .recorded import make_client

REPO = Path(__file__).resolve().parents[1]
REC = REPO / "tests" / "fixtures" / "recorded"
CG, BSV, CB, GCW = (REC / f"{k}_2026-10-06" for k in ("coingate", "buysellvouchers", "cardbear", "giftcardwiki"))
NOW = datetime(2026, 10, 6, 10, 40, tzinfo=UTC)
AGG_KEYS = ("coingate", "buysellvouchers", "cardbear", "giftcardwiki")


def prod_conf() -> dict:
    return tomllib.load(open(REPO / "config" / "production.toml", "rb"))


def conn_entry(key: str) -> dict:
    return next(c for c in prod_conf()["connectors"] if c["key"] == key)


def html_routes(d: Path) -> dict:
    meta = json.loads((d / "meta.json").read_text())
    return {m["url"]: (m["http_status"], {"content-type": m["content_type"]}, (d / f).read_bytes())
            for f, m in meta["files"].items()}


class McpReplay:
    """Fake MCP server replaying the recorded tools/call answers; refuses anything not recorded."""

    def __init__(self, d: Path = CG, overrides: dict | None = None, content_type: str = "application/json") -> None:
        meta = json.loads((d / "meta.json").read_text())
        self.robots = (d / "robots.txt").read_bytes()
        self.calls: dict[str, dict] = {}
        for f, m in meta["files"].items():
            if "mcp_tool" in m:
                self.calls[json.dumps([m["mcp_tool"], m["mcp_arguments"]], sort_keys=True)] = json.loads((d / f).read_text())
        self.overrides = overrides or {}
        self.content_type = content_type
        self.seen: list[dict] = []

    def __call__(self, *, method, url, ip, headers, body, timeout, max_bytes):
        if url.endswith("/robots.txt"):
            return TransportResponse(200, {"content-type": "text/plain"}, self.robots)
        req = json.loads(body)
        self.seen.append({"req": req, "headers": headers, "method": method, "url": url})
        if req["method"] == "initialize":
            ans = {"jsonrpc": "2.0", "id": req["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {}}}
        else:
            k = json.dumps([req["params"]["name"], req["params"]["arguments"]], sort_keys=True)
            ans = self.overrides.get(req["params"]["arguments"].get("brand") or req["params"]["arguments"].get("category"))
            if ans is None:
                ans = self.calls.get(k)
            if ans is None:
                return TransportResponse(404, {"content-type": "text/plain"}, b"not recorded")
            if isinstance(ans, TransportResponse):
                return ans
            ans = dict(ans, id=req["id"])
        data = json.dumps(ans).encode()
        if self.content_type == "text/event-stream":
            data = b"event: message\ndata: " + data + b"\n\n"
        return TransportResponse(200, {"content-type": self.content_type}, data)


def make(key: str, routes=None, transport=None, **kw):
    e = conn_entry(key)
    cfg_cls, _ = AGGREGATOR_KINDS[e["kind"]]
    cfg = cfg_cls.model_validate(e["options"])
    rec = {"buysellvouchers": BSV, "cardbear": CB, "giftcardwiki": GCW}.get(key)
    client, tr, clock = make_client(routes if routes is not None else (html_routes(rec) if rec else {}),
                                    allowed=(cfg.host,), **kw)
    if transport is not None:
        client.transport = tr = transport
    client.source_key = cfg.source_key
    return build_aggregator(e["kind"], e["options"], client=client), tr, clock


# ------------------------------------------------------------------ fixtures / config
def test_fixtures_dated_and_free_of_personal_data():
    for d in (CG, BSV, CB, GCW):
        meta = json.loads((d / "meta.json").read_text())
        assert d.name.endswith("2026-10-06")
        for f, m in meta["files"].items():
            assert m["fetched_at_utc"].startswith("2026-10-06")
            if f == "robots.txt":
                continue
            body = (d / f).read_text()
            for bad in ("username", "feedbacks", "user_level", "banner_description", "Set-Cookie", "@gmail", "email\":"):
                assert bad not in body, (f, bad)
    from value_rail.connectors.aggregators import bsv_products
    for f in BSV.glob("*.html"):
        arr, _ = bsv_products("t", str(f), f.read_text())
        for p in arr:
            assert p["user_id"].startswith("anon-") and set(p["user"]) <= {"userSellers"}
            assert set(p["user"].get("userSellers", {})) <= {"store_name"}


def test_config_wires_daily_discovery_only_jobs():
    conf = prod_conf()
    jobs = {j["connector"]: j for j in conf["jobs"] if j.get("connector")}
    for key in AGG_KEYS:
        e = conn_entry(key)
        assert e["kind"] in AGGREGATOR_KINDS and e["enabled"]
        assert jobs[key]["interval_seconds"] == 86400 and jobs[key]["enabled"]
        c, _, _ = make(key)
        assert c.source.role == SourceRole.DISCOVERY_ONLY and c.source.kind == SourceKind.AGGREGATOR
        caps = c.capabilities()
        assert not caps.checkout_quote and not caps.exit_quote and "discovery_only" in caps.notes
        assert c.PARSER_VERSION in caps.notes
    blocked = {c["key"]: c for c in conf["connectors"] if c["kind"] == "blocked"}
    assert "gcx" in blocked and "ggdeals" in blocked
    assert not any(j.get("connector") in ("gcx", "ggdeals") for j in conf["jobs"])


def test_role_cannot_be_configured_and_politeness_floor():
    opts = dict(conn_entry("buysellvouchers")["options"])
    with pytest.raises(ValidationError):
        BsvListConfig.model_validate(opts | {"role": "price_basis"})
    with pytest.raises(ValidationError):
        BsvListConfig.model_validate(opts | {"min_interval_s": 2})
    with pytest.raises(ValidationError):
        BsvPage(path="/en/products/list/bitsa-gift-card/?pageSize=50")
    with pytest.raises(ValidationError):
        BsvPage(path="/en/products/buy/102874/")
    with pytest.raises(ValidationError):
        CardBearPage(path="/r.php")


def test_face_from_title():
    assert face_from_title("Bitsa Euro Area - 100 EUR") == (100, "EUR")
    assert face_from_title("Azteco Bitcoin Crypto Voucher On Chain USD100") == (100, "USD")
    assert face_from_title("BITSA 50EUR") == (50, "EUR")
    assert face_from_title("Steam Wallet") == ("unknown", "unknown")


# ------------------------------------------------------------------ CoinGate MCP
def test_coingate_discovery_from_recorded_mcp():
    replay = McpReplay()
    c, _, _ = make("coingate", transport=replay)
    items = c.discovery(NOW)
    assert not [i for i in items if i.meta.get("page_error")]
    # initialize first, protocol headers, only read-only tools, never an email
    assert replay.seen[0]["req"]["method"] == "initialize"
    tools = {s["req"]["params"]["name"] for s in replay.seen[1:]}
    assert tools <= {"get_gift_card", "search_gift_cards"}
    for s in replay.seen:
        assert s["method"] == "POST" and s["headers"]["mcp-protocol-version"] == "2025-06-18"
        assert "text/event-stream" in s["headers"]["Accept"] and "Cookie" not in s["headers"]
        assert "email" not in json.dumps(s["req"])
    bitsa = [i for i in items if i.meta["target_id"] == "card-bitsa-de"]
    assert len(bitsa) >= 5
    it = next(i for i in bitsa if str(i.product.face_value) in ("100", "100.0"))
    o = c.normalize(it, c.offer_fetch(it, NOW)[0], NOW)
    assert o.source.role == SourceRole.DISCOVERY_ONLY and o.currency == "EUR"
    assert o.raw["seller"].startswith("CoinGate Gift Cards") and o.raw["seller_link"].startswith("https://coingate.com/")
    assert o.fees[0].required and o.fees[0].amount == "unknown"
    ev = o.evidence[0].payload
    assert ev["parser_version"] == "coingate-mcp/1.0.0" and ev["source_role"] == "discovery_only"
    assert ev["robots_txt_checked"] is True
    # clearance lists: explicit, schema-valid 0 results (DE) are an observation, not an error
    assert any("search-clearance-stock-de" in u or "clearance-stock" in u for u in c.ok_pages)
    assert {"search-clearance-stock-de", "search-clearance-stock-ww"} <= set(c._pages)


def test_coingate_refuses_order_tools_and_email():
    c, _, _ = make("coingate", transport=McpReplay())
    for tool in ("create_order", "quote_order", "get_order", "notify_when_in_stock", "list_payment_methods"):
        with pytest.raises(PermissionError):
            c.call_tool(tool, {})
    with pytest.raises(PermissionError):
        c.call_tool("get_gift_card", {"brand": "bitsa", "email": "x@example.com"})


def test_coingate_sse_answer_is_decoded():
    c, _, _ = make("coingate", transport=McpReplay(content_type="text/event-stream"))
    items = c.discovery(NOW)
    assert len([i for i in items if not i.meta.get("page_error")]) > 10


def test_coingate_errors_are_distinct_not_zero_offers():
    err = {"jsonrpc": "2.0", "id": 0, "error": {"code": -32602, "message": "bad brand"}}
    tool_err = {"jsonrpc": "2.0", "id": 0, "result": {"isError": True, "content": [{"type": "text", "text": "boom"}]}}
    schema = {"jsonrpc": "2.0", "id": 0, "result": {"structuredContent": {"brand": {}, "items": []}}}
    limited = TransportResponse(429, {"retry-after": "60"}, b"")
    replay = McpReplay(overrides={"bitsa": err, "paysafecard": tool_err, "flexepin": schema, "cashlib": limited})
    c, _, _ = make("coingate", transport=replay, retries=0)
    items = c.discovery(NOW)
    errs = {k: type(v) for k, v in c._errors.items()}
    assert errs["card-bitsa-de"] is UpstreamError and errs["card-paysafecard-de"] is UpstreamError
    assert errs["card-flexepin-de"] is ParserBroken and errs["card-cashlib-de"] is RateLimited
    page_items = [i for i in items if i.meta.get("page_error")]
    assert len(page_items) == 4
    with pytest.raises(RateLimited):
        c.offer_fetch(next(i for i in page_items if i.meta["target_id"] == "card-cashlib-de"), NOW)


def test_coingate_search_empty_without_empty_ok_is_unexpected_empty():
    sc = {"total_results": 0, "total_pages": 0, "results": []}
    assert parse_coingate_search("cg", CoinGateSearch(category="x", country="DE", empty_ok=True), "u", sc)[0] == []
    with pytest.raises(UnexpectedEmpty):
        parse_coingate_search("cg", CoinGateSearch(category="x", country="DE"), "u", sc)
    with pytest.raises(ParserBroken):
        parse_coingate_search("cg", CoinGateSearch(category="x", country="DE"), "u", {"brands": []})
    with pytest.raises(UnexpectedEmpty):
        parse_coingate_gift_card("cg", CoinGateBrand(brand="x", country="DE"), "u", {"products": []})


def test_mcp_decode_text_content_fallback_and_missing_id():
    from value_rail.connectors.aggregators import _mcp_payload
    msg = {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "{\"products\": []}"}]}}
    assert _mcp_payload(msg, "cg", "u", "get_gift_card") == {"products": []}
    with pytest.raises(ParserBroken):
        _mcp_decode(b'{"jsonrpc":"2.0","id":9,"result":{}}', "application/json", 3, "cg", "u")
    with pytest.raises(ParserBroken):
        _mcp_decode(b"<html>challenge</html>", "text/html", 3, "cg", "u")


# ------------------------------------------------------------------ BuySellVouchers
def test_bsv_parses_listings_with_seller_and_eur_prices():
    c, transport, clock = make("buysellvouchers")
    items = c.discovery(NOW)
    assert not [i for i in items if i.meta.get("page_error")]
    by_t: dict[str, list] = {}
    for i in items:
        by_t.setdefault(i.meta["target_id"], []).append(i)
    assert len(by_t["bitsa-gift-card"]) >= 5 and len(by_t["paysafe-virtual-cards"]) >= 5
    assert "bitnovo-voucher" not in by_t  # explicitly empty category (empty_ok) -> page ok, no leads
    assert any(u.endswith("/bitnovo-voucher/") for u in c.ok_pages)
    psc = [i for i in by_t["paysafe-virtual-cards"] if i.product.region == "DE"]
    assert psc and all(i.product.face_currency == "EUR" for i in psc)
    it = psc[0]
    o = c.normalize(it, c.offer_fetch(it, NOW)[0], NOW)
    assert o.currency == "EUR" and o.unit_price != "unknown" and o.source.role == SourceRole.DISCOVERY_ONLY
    assert o.raw["seller"] == "EliteLoops"
    assert o.evidence[0].payload["parser_version"] == "bsv-rsc-list/1.0.0"
    # politeness: >= 5 s between requests to the host, never a buy/feedback/query URL
    assert all(s >= 5 for s in clock.sleeps)
    urls = [call["url"] for call in transport.calls]
    assert not any("/buy/" in u or "?" in u or "feedbacks" in u for u in urls)


def test_bsv_individual_sellers_are_pseudonymised():
    t = BsvPage(id="bitsa", path="/en/products/list/bitsa-gift-card/")
    pg = parse_bsv_list("bsv", t, "u", 200, (BSV / "bitsa-gift-card.html").read_bytes())
    sellers = {ld.seller for ld in pg.leads}
    assert "EliteLoops" in sellers
    assert all(s == "EliteLoops" or s.startswith("bsv-seller-") for s in sellers)


def test_bsv_layout_change_and_empty_are_distinct():
    t = BsvPage(id="x", path="/en/products/list/x/")
    with pytest.raises(ParserBroken):
        parse_bsv_list("bsv", t, "u", 200, b"<html><body>no flight data</body></html>")
    empty = (BSV / "bitnovo-voucher.html").read_bytes()
    with pytest.raises(UnexpectedEmpty):
        parse_bsv_list("bsv", t, "u", 200, empty)
    assert parse_bsv_list("bsv", t.model_copy(update={"empty_ok": True}), "u", 200, empty).leads == []


def test_bsv_403_and_429_are_reported_not_zero_offers():
    routes = html_routes(BSV)
    routes["https://www.buysellvouchers.com/en/products/list/bitsa-gift-card/"] = (403, {"content-type": "text/html"}, b"")
    routes["https://www.buysellvouchers.com/en/products/list/neosurf-voucher/"] = (429, {"content-type": "text/html"}, b"")
    c, _, _ = make("buysellvouchers", routes=routes, retries=0)
    c.discovery(NOW)
    assert type(c._errors["bitsa-gift-card"]) is AccessDenied
    assert type(c._errors["neosurf-voucher"]) is RateLimited


def test_bsv_robots_change_is_respected():
    routes = html_routes(BSV)
    routes["https://www.buysellvouchers.com/robots.txt"] = (200, {"content-type": "text/plain"},
                                                            b"User-agent: *\nDisallow: /en/products/list/\n")
    c, transport, _ = make("buysellvouchers", routes=routes)
    c.discovery(NOW)
    assert all(type(e) is RobotsDisallowed for e in c._errors.values()) and len(c._errors) == 5
    assert [x["url"] for x in transport.calls] == ["https://www.buysellvouchers.com/robots.txt"]


# ------------------------------------------------------------------ CardBear
def test_cardbear_discount_leads_and_outbound_links_never_followed():
    c, transport, _ = make("cardbear")
    items = c.discovery(NOW)
    assert not [i for i in items if i.meta.get("page_error")] and items
    it = next(i for i in items if i.meta["target_id"] == "amazon")
    o = c.normalize(it, c.offer_fetch(it, NOW)[0], NOW)
    assert o.unit_price == "unknown" and o.raw["discount_percent"] is not None
    assert o.raw["seller_link"].startswith("https://www.cardbear.com/r.php")
    assert o.evidence[0].payload["parser_version"] == "cardbear-html/1.0.0"
    assert not any("r.php" in x["url"] for x in transport.calls)


def test_cardbear_layout_change_is_parser_broken():
    t = CardBearPage(id="x", path="/gift-card-discount/1/x")
    with pytest.raises(ParserBroken):
        parse_cardbear("cb", t, "u", 200, b"<html><title>X Gift Card</title><body>new layout</body></html>")
    with pytest.raises(UnexpectedEmpty):
        parse_cardbear("cb", t, "u", 200, b'<html><div role="table"><div role="row"><div role="columnheader">Seller'
                                          b'</div></div></div><h2>x</h2></html>')


# ------------------------------------------------------------------ GiftCardWiki
def test_gcw_hot_deals_brand_leads():
    c, _, _ = make("giftcardwiki")
    items = c.discovery(NOW)
    assert len(items) >= 5 and not [i for i in items if i.meta.get("page_error")]
    o = c.normalize(items[0], c.offer_fetch(items[0], NOW)[0], NOW)
    assert o.unit_price == "unknown" and o.raw["discount_percent"]
    assert o.evidence[0].payload["parser_version"] == "gcw-hotdeals/1.0.0"


def test_gcw_layout_change_and_empty():
    from value_rail.connectors.aggregators import AggTarget
    with pytest.raises(ParserBroken):
        parse_gcw_hotdeals("g", AggTarget(id="h"), "u", 200, b"<html>redesign</html>")
    with pytest.raises(UnexpectedEmpty):
        parse_gcw_hotdeals("g", AggTarget(id="h"), "u", 200, b"<h4>Filter by Brand</h4><table></table>")


# ------------------------------------------------------------------ pipeline: never a Preisfund / alert
@pytest.mark.parametrize("key", AGG_KEYS)
def test_aggregator_scan_is_blocked_never_price_find_or_alert(ctx, key):
    c, _, _ = make(key, transport=McpReplay() if key == "coingate" else None)
    rep = run_scan(ctx.session_factory, c, ctx.settings, NOW, trigger="test")
    assert rep.items_seen > 0 and rep.evaluations_created > 0
    assert rep.alerts_enqueued == 0
    assert set(rep.statuses.values()) == {RouteStatus.BLOCKED.value}
    from value_rail.storage.orm import RouteEvaluationRow
    with ctx.session_factory() as s:
        reasons = [s.get(RouteEvaluationRow, i).outputs["block_reasons"] for i in rep.evaluation_ids.values()]
    if key in ("coingate", "buysellvouchers"):  # leads with a face value: blocked BECAUSE aggregator-only
        assert any("direct_price_unverified:only_discovery_only_offers" in r for r in reasons)
    else:  # discount-only leads (no face value/price) cannot even be identified
        assert all("face_value_unknown" in r for r in reasons)
