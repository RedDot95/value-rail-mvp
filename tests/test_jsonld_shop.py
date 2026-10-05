"""Offline tests for the generic JSON-LD Product.offers connector (dundle direct seller, GAMIVO marketplace)."""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from value_rail.connectors.jsonld_shop import (JsonLdShopConfig, JsonLdShopConnector, ShopPage, face_value_from,
                                               parse_shop_page)
from value_rail.domain.enums import SourceKind, SourceRole
from value_rail.net.errors import AccessDenied, ParserBroken, UnexpectedEmpty, UpstreamError

from .recorded import FakeClock, make_client

REPO = Path(__file__).resolve().parents[1]
REC = REPO / "tests" / "fixtures" / "recorded"
DUNDLE = REC / "dundle_com_de_2026-10-06"
GAMIVO = REC / "gamivo_com_2026-10-06"
NOW = datetime(2026, 10, 6, 0, 0, tzinfo=UTC)


def prod_options(key: str) -> dict:
    conf = tomllib.load(open(REPO / "config" / "production.toml", "rb"))
    return next(c for c in conf["connectors"] if c["key"] == key)["options"]


def routes_for(d: Path) -> dict:
    meta = json.loads((d / "meta.json").read_text())
    return {m["url"]: (m["http_status"], {"content-type": m["content_type"]}, (d / f).read_bytes())
            for f, m in meta["files"].items()}


def make(key: str, rec: Path, routes=None, **kw) -> tuple[JsonLdShopConnector, object, FakeClock]:
    cfg = JsonLdShopConfig.model_validate(prod_options(key))
    client, transport, clock = make_client(routes_for(rec) if routes is None else routes, allowed=(cfg.host,), **kw)
    client.source_key = cfg.source_key
    return JsonLdShopConnector(cfg, client=client), transport, clock


def test_fixture_meta_is_dated_and_stripped():
    for d in (DUNDLE, GAMIVO):
        meta = json.loads((d / "meta.json").read_text())
        assert d.name.endswith("2026-10-06")
        for f, m in meta["files"].items():
            assert m["fetched_at_utc"].startswith("2026-10-0")
            if f.endswith(".html"):
                body = (d / f).read_text()
                assert "cookie" not in body.lower().split("</title>")[0]
                assert "<script" in body and len(body) < 30_000  # stripped


def test_dundle_parses_all_denominations_with_face_value():
    c, _, _ = make("dundle", DUNDLE)
    p = c.config.pages[0]
    pg = parse_shop_page(c.config, p, "u", 200, (DUNDLE / "paysafecard.html").read_bytes())
    assert [o.sku for o in pg.offers][:2] == ["paysafecard-5-eur-de", "paysafecard-10-eur-de"]
    assert len(pg.offers) == 10 and all(o.seller == "dundle.com" and o.currency == "EUR" for o in pg.offers)
    assert {str(o.face_value) for o in pg.offers} == {"5", "10", "15", "20", "25", "30", "50", "75", "100", "150"}
    assert all(o.quantity == "unknown" for o in pg.offers)


def test_dundle_scan_items_offers_and_honest_fee():
    c, transport, clock = make("dundle", DUNDLE)
    items = c.discovery(NOW)
    assert len(items) == 14  # 10 paysafecard + 4 bitsa; azteco absent_ok -> 0
    assert all(not i.meta.get("page_error") for i in items)
    assert "https://dundle.com/de/azteco/" in c.ok_pages
    it = next(i for i in items if i.meta["sku"] == "bitsa-50-eur")
    assert it.product.region == "DE" and it.product.seller == "dundle.com" and it.product.redemption_program == "bitsa"
    raws = c.offer_fetch(it, NOW)
    o = c.normalize(it, raws[0], NOW)
    assert str(o.unit_price) == "50" and o.currency == "EUR" and not o.price_includes_fees
    fee = o.fees[0]
    assert fee.required and fee.amount == "unknown"
    ev = o.evidence[0].payload
    assert ev["parser_version"] == "jsonld-offers/1.0.0" and ev["robots_txt_checked"] is True
    assert o.raw["seller_offer"]["offer_key"] == "dundle-com|bitsa-50-eur"
    assert o.source.kind == SourceKind.DIRECT_SELLER and o.source.role == SourceRole.PRICE_BASIS
    caps = c.capabilities()
    assert caps.checkout_quote is False and caps.exit_quote is False and caps.live_network
    # politeness: robots first, >= 5 s between page requests
    urls = [x["url"] for x in transport.calls]
    assert urls[0] == "https://dundle.com/robots.txt"
    assert all(s >= 5.0 for s in clock.sleeps) and len(clock.sleeps) >= 2


def test_tiers_select_pages():
    c, transport, _ = make("dundle", DUNDLE)
    c.configure_for_job({"tiers": ["watch"]})
    c.discovery(NOW)
    assert not any("azteco" in x["url"] for x in transport.calls)
    c.configure_for_job({})
    assert len(c.selected_pages()) == 3


def test_gamivo_marketplace_seller_offers():
    c, _, _ = make("gamivo", GAMIVO)
    c.configure_for_job({"tiers": ["watch"]})
    c.config.pages = [p for p in c.config.pages if p.path.endswith("flexepin-eur-50")]
    items = c.discovery(NOW)
    sellers = sorted(i.meta["seller"] for i in items)
    assert sellers == ["Digital Galaxy", "Smart_Solutions", "Top-Notch Keys", "Ultimate Choice", "zero zero"]
    assert len({i.route_key for i in items}) == 5
    it = next(i for i in items if i.meta["seller"] == "Smart_Solutions")
    o = c.normalize(it, c.offer_fetch(it, NOW)[0], NOW)
    assert str(o.unit_price) == "54.38"  # cheapest of the seller's two offers (duplicate kept as count)
    assert o.raw["duplicates"] == 1 and o.identity.seller == "Smart_Solutions" and str(o.identity.face_value) == "50"
    assert o.source.kind == SourceKind.MARKETPLACE and o.source.role == SourceRole.PRICE_BASIS


def test_gamivo_cloudflare_challenge_is_access_denied_not_empty():
    meta = routes_for(GAMIVO)
    meta["https://www.gamivo.com/product/flexepin-eur-50"] = (403, {"content-type": "text/html", "cf-mitigated": "challenge"},
                                                              b"<title>Just a moment...</title>")
    c, _, _ = make("gamivo", GAMIVO, routes=meta)
    c.config.pages = [p for p in c.config.pages if p.path.endswith("flexepin-eur-50")]
    items = c.discovery(NOW)
    assert len(items) == 1 and items[0].meta["page_error"]
    with pytest.raises(AccessDenied):
        c.offer_fetch(items[0], NOW)


def test_missing_product_is_parser_broken_unless_absent_ok():
    cfg = JsonLdShopConfig.model_validate(prod_options("dundle"))
    body = (DUNDLE / "azteco.html").read_bytes()
    with pytest.raises(ParserBroken):
        parse_shop_page(cfg, ShopPage(path="/x/", family="f", redemption_program="r", region="DE"), "u", 200, body)
    assert parse_shop_page(cfg, cfg.pages[2], "u", 200, body).absent


def test_marketplace_offer_without_seller_is_parser_broken():
    cfg = JsonLdShopConfig.model_validate(prod_options("gamivo"))
    body = b'<script type="application/ld+json">{"@type":"Product","name":"X 50 EUR","offers":[{"@type":"Offer","price":1,"priceCurrency":"EUR"}]}</script>'
    with pytest.raises(ParserBroken):
        parse_shop_page(cfg, cfg.pages[0], "u", 200, body)


def test_aggregate_offer_only_is_unexpected_empty_and_unquoted_type():
    cfg = JsonLdShopConfig.model_validate(prod_options("dundle"))
    body = (b'<script type=application/ld+json>[{"@type":"Product","name":"Azteco","offers":[{"@type":"AggregateOffer",'
            b'"lowPrice":"1","highPrice":"150","priceCurrency":"EUR"}]}]</script>')
    with pytest.raises(UnexpectedEmpty):
        parse_shop_page(cfg, cfg.pages[0], "u", 200, body)


def test_404_page_is_upstream_error():
    r = routes_for(DUNDLE)
    del r["https://dundle.com/de/bitsa/"]
    c, _, _ = make("dundle", DUNDLE, routes=r)
    items = c.discovery(NOW)
    err = next(i for i in items if i.meta.get("page_error"))
    with pytest.raises(UpstreamError):
        c.offer_fetch(err, NOW)


def test_config_guards():
    with pytest.raises(ValueError):
        JsonLdShopConfig(source_key="x", source_name="x", host="h", source_kind="marketplace", min_interval_s=1)
    with pytest.raises(ValueError):
        JsonLdShopConfig(source_key="x", source_name="x", host="h", source_kind="direct_seller")
    agg = JsonLdShopConfig(source_key="x", source_name="x", host="h", source_kind="aggregator")
    assert agg.role == SourceRole.DISCOVERY_ONLY


@pytest.mark.parametrize("texts,expected", [(("paysafecard-50-eur-de", "", ""), "50"), (("", "", "Flexepin EU EUR €100"), "100"),
                                            (("bitsa-10-eur", "", ""), "10"), (("", "", "Gift card"), "unknown")])
def test_face_value_parsing(texts, expected):
    assert str(face_value_from(*texts)[0]) == expected
