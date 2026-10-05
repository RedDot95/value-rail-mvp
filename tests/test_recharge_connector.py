"""Recharge.com connector against RECORDED real responses (2026-10-05), fully offline."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from value_rail.connectors.recharge import (PARSER_VERSION, RechargeConfig, RechargeConnector, face_value_of,
                                            parse_page)
from value_rail.net.errors import ParserBroken, UnexpectedEmpty
from value_rail.storage.orm import EvidenceRow, QuoteRow, RouteEvaluationRow, SourceRow
from value_rail.worker.scan import run_scan

from .recorded import REC, make_client, recorded_routes

SCAN_NOW = datetime(2026, 10, 5, 21, 45, tzinfo=UTC)
BITSA = "https://www.recharge.com/en/de/bitsa"
PSC = "https://www.recharge.com/en/de/paysafecard"


def connector(routes=None) -> tuple[RechargeConnector, object]:
    client, transport, _ = make_client(routes)
    return RechargeConnector(RechargeConfig(), client=client), transport


def test_recorded_fixture_contains_no_personal_data():
    import re
    for p in REC.glob("*.html"):
        t = p.read_text()
        assert not re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", t)
        assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", t)
        assert "set-cookie" not in t.lower()


def test_parse_recorded_bitsa_and_paysafecard():
    b = parse_page("recharge-com-de", BITSA, 200, (REC / "bitsa.html").read_bytes())
    p = parse_page("recharge-com-de", PSC, 200, (REC / "paysafecard.html").read_bytes())
    assert [v.sku for v in b.variants] == ["15-eur", "25-eur", "50-eur", "100-eur"]
    assert [face_value_of(v)[0] for v in p.variants] == [Decimal(x) for x in ("10", "20", "30", "50", "100", "150")]
    assert all(v.currency == "EUR" and v.price == v.voucher_value and v.service_fee_from == "0" for v in b.variants + p.variants)
    assert b.product_group_name == "BITSA" and len(b.jsonld_sha256) == 64


def test_discovery_identity_complete_and_robots_first():
    c, transport = connector()
    items = c.discovery(SCAN_NOW)
    assert transport.calls[0]["url"] == "https://www.recharge.com/robots.txt"
    assert {x["url"] for x in transport.calls[1:]} == {BITSA, PSC}
    assert len(items) == 10
    it = next(i for i in items if i.route_key == "recharge-de:paysafecard:150-eur")
    pid = it.product
    assert (pid.face_value, pid.face_currency, pid.region, pid.variant, pid.seller, pid.redemption_program) == \
        (Decimal("150"), "EUR", "DE", "digital-code:150-eur", "recharge.com", "paysafecard")
    assert c.capabilities().checkout_quote is False and c.capabilities().exit_quote is False


def test_normalize_unknown_service_fee_and_evidence():
    c, _ = connector()
    item = next(i for i in c.discovery(SCAN_NOW) if i.route_key == "recharge-de:bitsa:50-eur")
    raw = c.offer_fetch(item, SCAN_NOW)[0]
    o = c.normalize(item, raw, SCAN_NOW)
    assert o.unit_price == Decimal("50") and o.currency == "EUR" and o.price_includes_fees is False
    assert [(f.name, f.amount, f.required) for f in o.fees] == [("recharge_service_fee", "unknown", True)]
    assert o.advertised_quantity.value == "unknown" and "InStock" in o.advertised_quantity.scope
    ev = o.evidence[0]
    assert ev.payload["parser_version"] == PARSER_VERSION and ev.payload["url"] == BITSA
    assert ev.payload["http_status"] == 200 and ev.payload["variant_jsonld"]["sku"] == "50-eur"


def test_full_scan_recorded_all_blocked_never_price_find(ctx):
    c, _ = connector()
    rep = run_scan(ctx.session_factory, c, ctx.settings, SCAN_NOW, trigger="test")
    assert rep.status.value == "ok" and rep.evaluations_created == 10 and rep.sources_failed == {}
    assert set(rep.statuses.values()) == {"blocked"}
    with ctx.session_factory() as s:
        evs = s.scalars(select(RouteEvaluationRow).where(RouteEvaluationRow.scan_run_id == rep.scan_run_id)).all()
        for ev in evs:
            assert "unknown_required_fee:recharge_service_fee" in ev.outputs["block_reasons"]
            assert ev.outputs["profit_eur"] == "unknown" and ev.is_synthetic is False
        psc = next(e for e in evs if e.route_key == "recharge-de:paysafecard:100-eur")
        # sourced exit rule attached (5 % max 5 EUR), prerequisites unproven -> cannot verify
        assert psc.inputs["exit_quote"]["venue_key"] == "rule-exit:paysafecard-de-issuer-refund"
        assert psc.inputs["exit_quote"]["depth_quantity"] == 1
        assert "prerequisite:paysafecard_refund_identity_verification_de_bank_account" in psc.outputs["missing_evidence"]
        assert "checkout_quote" in psc.outputs["missing_evidence"]
        bitsa = next(e for e in evs if e.route_key == "recharge-de:bitsa:100-eur")
        assert "unknown_required_fee:bitsa_voucher_reload_fee" in bitsa.outputs["block_reasons"]
        assert bitsa.inputs["exit_quote"]["depth_quantity"] == 5  # 500 EUR/day SEPA limit / 100 EUR face
        src = s.scalar(select(SourceRow).where(SourceRow.key == "recharge-com-de"))
        assert src.health == "ok" and src.is_synthetic is False
        evidence = s.scalars(select(EvidenceRow).where(EvidenceRow.subject_ref.like("offer_snapshot:%"))).all()
        assert evidence and all(e.payload["parser_version"] == PARSER_VERSION for e in evidence)
        assert s.scalars(select(QuoteRow).where(QuoteRow.kind == "checkout")).all() == []


def test_parser_break_is_disturbance_not_zero_offers(ctx):
    routes = recorded_routes()
    routes[BITSA] = (200, {"content-type": "text/html"}, b"<html><body>new layout</body></html>")
    c, _ = connector(routes)
    rep = run_scan(ctx.session_factory, c, ctx.settings, SCAN_NOW)
    assert rep.status.value == "degraded"
    assert "[parser_broken]" in rep.sources_failed["recharge-com-de"]
    assert rep.evaluations_created == 6  # paysafecard page still evaluated
    assert not any(k.startswith("recharge-de:bitsa:") and not k.endswith(":page") for k in rep.statuses)


def test_unexpected_empty_variants():
    html = (REC / "bitsa.html").read_text()
    start = html.index('"hasVariant"')
    end = html.index("]", html.index("[", start)) + 1
    # rebuild via JSON to keep it valid
    import re
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    g = json.loads(blocks[-1])
    g["hasVariant"] = []
    body = f'<script type="application/ld+json">{json.dumps(g)}</script>'.encode()
    assert start < end
    with pytest.raises(UnexpectedEmpty):
        parse_page("recharge-com-de", BITSA, 200, body)
    g.pop("hasVariant")
    with pytest.raises(ParserBroken):
        parse_page("recharge-com-de", BITSA, 200, f'<script type="application/ld+json">{json.dumps(g)}</script>'.encode())


@pytest.mark.parametrize("status,code", [(429, "rate_limited_429"), (403, "access_denied_403"), (404, "upstream_error")])
def test_http_errors_mark_source_down(ctx, status, code):
    routes = recorded_routes()
    routes[PSC] = (status, {"content-type": "text/html"}, b"")
    c, _ = connector(routes)
    rep = run_scan(ctx.session_factory, c, ctx.settings, SCAN_NOW)
    assert rep.status.value == "degraded" and f"[{code}]" in rep.sources_failed["recharge-com-de"]
    assert rep.evaluations_created == 4


def test_all_pages_failing_is_failed_scan(ctx):
    routes = recorded_routes()
    routes[PSC] = routes[BITSA] = (403, {}, b"")
    c, _ = connector(routes)
    rep = run_scan(ctx.session_factory, c, ctx.settings, SCAN_NOW)
    assert rep.evaluations_created == 0 and rep.sources_failed
    assert rep.status.value in ("degraded", "failed")
    with ctx.session_factory() as s:
        assert s.scalar(select(SourceRow).where(SourceRow.key == "recharge-com-de")).health == "down"


def test_face_value_unknown_stays_unknown():
    g = {"@type": "ProductGroup", "name": "X", "hasVariant": [
        {"name": "Mystery code", "sku": "m", "offers": {"price": "9", "priceCurrency": "EUR"}}]}
    p = parse_page("recharge-com-de", BITSA, 200, f'<script type="application/ld+json">{json.dumps(g)}</script>'.encode())
    assert face_value_of(p.variants[0]) == ("unknown", "unknown")
    g["hasVariant"][0]["name"] = "Thing 20 EUR"
    p = parse_page("recharge-com-de", BITSA, 200, f'<script type="application/ld+json">{json.dumps(g)}</script>'.encode())
    assert face_value_of(p.variants[0]) == (Decimal("20"), "jsonld:name")


def test_rescan_after_rule_review_date_expires_exit(ctx):
    c, _ = connector()
    rep = run_scan(ctx.session_factory, c, ctx.settings, datetime(2026, 11, 6, tzinfo=UTC))
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow, rep.evaluation_ids["recharge-de:paysafecard:50-eur"])
        assert "exit_quote_stale" in ev.outputs["stale_reasons"]
        assert ev.status == "blocked"  # still blocked: unknown service fee dominates


def test_smoke_report_offline_with_recorded_connector(ctx, tmp_path):
    from value_rail.smoke import run_smoke
    c, _ = connector()
    rep, md = run_smoke(ctx, "recharge", out_dir=tmp_path, now=SCAN_NOW, connector=c)
    assert rep.evaluations_created == 10
    f = tmp_path / "live_smoke_2026-10-05.md"
    assert f.exists() and "23:45:00 CEST" in md and "Angebote (Offer-Snapshots) gespeichert: **10**" in md
    assert "Preisfunde: **0**" in md
