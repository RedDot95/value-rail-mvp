"""Candidate signals: simulation only, including persistence and notification delivery."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from value_rail.alerts.dispatcher import dispatch_pending
from value_rail.alerts.eligibility import delivery_check
from value_rail.alerts.sinks import MemorySink, TelegramAlertSink
from value_rail.connectors.base import Connector, ConnectorCapabilities, DiscoveryItem, NormalizedOffer, RawOffer, SourceSpec
from value_rail.coverage import coverage_report
from value_rail.domain.entities import QuantityObservation
from value_rail.domain.identity import ProductIdentity
from value_rail.evidence import EvidenceDraft
from value_rail.storage.orm import RouteEvaluationRow
from value_rail.valuation.engine import evaluate_route
from value_rail.valuation.models import FeeComponent, OfferInput, RouteInputs, RuleParams
from value_rail.valuation.replay import replay_evaluation
from value_rail.worker.scan import run_scan

PRODUCT = ProductIdentity(face_value="100", face_currency="EUR", region="unknown", variant="digital", seller="TEST-ONLY", redemption_program="abon")
RULE = RuleParams(evaluation_mode="screener", label="TEST-ONLY-screener", price_find_min_discount="0.01")


def listing(now, **updates):
    offer = OfferInput(offer_ref="offer:1", source_key="TEST-ONLY", source_role="discovery_only", identity=PRODUCT,
                       unit_price="95", currency="EUR", captured_at=now, evidence_refs=["TEST-ONLY evidence"],
                       fees=[FeeComponent(name="unknown fee", kind="fixed_per_order", amount="unknown")],
                       listing_url="https://example.com/listing")
    return offer.model_copy(update=updates)


def evaluate(now, **updates):
    return evaluate_route(RouteInputs(route_key="TEST-ONLY", product=PRODUCT, offers=[listing(now, **updates)], evaluated_at=now), RULE)


def test_unknown_fees_and_exit_do_not_block_candidate(now):
    result = evaluate(now)
    assert result.status == "price_find" and result.discount == Decimal("0.05")
    assert result.profit_eur == result.net_exit_eur == result.unit_all_in_eur == "unknown"
    assert not result.missing_evidence and result.screening["region"] == "unknown"


@pytest.mark.parametrize("change", [dict(unit_price="unknown"), dict(unit_price=Decimal("100")),
    dict(unit_price=Decimal("99.5")), dict(unit_price=Decimal("0")), dict(currency="USD"), dict(evidence_refs=[]),
    dict(advertised_quantity=QuantityObservation(value=0)), dict(source_role="exit")])
def test_no_signal_without_concrete_discounted_available_listing(now, change):
    assert evaluate(now, **change).status != "price_find"


@pytest.mark.parametrize("offset", [-3601, 1])
def test_old_and_future_prices_do_not_signal(now, offset):
    assert evaluate(now, captured_at=now + timedelta(seconds=offset)).status == "expired"


def test_cross_seller_identity_and_unsafe_link(now):
    assert evaluate(now, identity=PRODUCT.model_copy(update={"seller": "OTHER"})).status == "blocked"
    assert evaluate(now, listing_url="https://secret:password@example.com/").screening["listing_url"] is None


class SimulatedListing(Connector):
    key = "TEST-ONLY"
    price = Decimal("95")
    quantity = 3
    source = SourceSpec(key=key, name=key, kind="marketplace", role="discovery_only")

    def capabilities(self):
        return ConnectorCapabilities(discovery=True, offer_fetch=True, normalize=True)

    def discovery(self, now):
        return [DiscoveryItem(route_key=self.key, product=PRODUCT, product_family="abon", sources=[self.source], prerequisites=["account_missing"])]

    def offer_fetch(self, item, now):
        return [RawOffer(source_key=self.key, fetched_at=now, payload={})]

    def normalize(self, item, raw, now):
        return NormalizedOffer(source=self.source, identity=PRODUCT, unit_price=self.price, currency="EUR",
            price_text_raw=str(self.price), price_includes_fees=False,
            fees=[FeeComponent(name="fee", kind="fixed_per_order", amount="unknown")],
            advertised_quantity=QuantityObservation(value=self.quantity), checkout_confirmed_quantity=QuantityObservation(),
            purchased_quantity=QuantityObservation(), captured_at=now, raw={"page_url": "https://example.com/listing"},
            evidence=[EvidenceDraft(kind="listing_snapshot", source_key=self.key, captured_at=now, summary="TEST-ONLY simulation")])


def configure(ctx, now):
    cfg = ctx.settings.file_config
    cfg.rules.evaluation_mode = "screener"
    cfg.rules.label = RULE.label
    cfg.rules.price_find_min_discount = RULE.price_find_min_discount
    cfg.alerts.alert_statuses = ["price_find"]
    cfg.scope.enabled = True
    ctx.seed(now=now)


def test_scan_push_replay_dedup_price_change_and_return(ctx, now):
    configure(ctx, now)
    connector, sink = SimulatedListing(), MemorySink()
    rep = run_scan(ctx.session_factory, connector, ctx.settings, now)
    assert rep.alerts_enqueued == 1
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow, rep.evaluation_ids[connector.key])
        assert ev.inputs["prerequisites"] == [] and ev.inputs["exit_quote"] is None
        assert replay_evaluation(s, ev.id).match
        assert len(coverage_report(s, ctx.settings, now)["candidate_signals_now"]) == 1
    assert dispatch_pending(ctx.session_factory, sink, now, eligibility=delivery_check(ctx.settings)).sent == 1
    text = TelegramAlertSink.format_text(sink.sent[0])
    assert "95 EUR" in text and "https://example.com/listing" in text and "Profit" not in text
    assert run_scan(ctx.session_factory, connector, ctx.settings, now + timedelta(seconds=10)).alerts_enqueued == 0
    connector.price = Decimal("90")
    assert run_scan(ctx.session_factory, connector, ctx.settings, now + timedelta(seconds=20)).alerts_enqueued == 1
    assert dispatch_pending(ctx.session_factory, sink, now + timedelta(seconds=20), eligibility=delivery_check(ctx.settings)).sent == 1
    connector.price = Decimal("100")
    assert run_scan(ctx.session_factory, connector, ctx.settings, now + timedelta(seconds=30)).alerts_enqueued == 0
    connector.price = Decimal("90")
    assert run_scan(ctx.session_factory, connector, ctx.settings, now + timedelta(seconds=40)).alerts_enqueued == 1
    assert dispatch_pending(ctx.session_factory, sink, now + timedelta(seconds=40), eligibility=delivery_check(ctx.settings)).sent == 1
    assert len({p["event_id"] for p in sink.sent}) == 3


@pytest.mark.parametrize("change", ["price", "stock", "stale", "source"])
def test_pending_signal_is_rechecked_before_push(ctx, now, change):
    from value_rail.storage.orm import SourceRow
    configure(ctx, now)
    connector, sink = SimulatedListing(), MemorySink()
    run_scan(ctx.session_factory, connector, ctx.settings, now)
    at = now + timedelta(seconds=10)
    if change == "price":
        connector.price = Decimal("100")
        run_scan(ctx.session_factory, connector, ctx.settings, at)
    elif change == "stock":
        connector.quantity = 0
        run_scan(ctx.session_factory, connector, ctx.settings, at)
    elif change == "stale":
        at = now + timedelta(seconds=3601)
    else:
        with ctx.session_factory.begin() as s:
            s.scalar(select(SourceRow).where(SourceRow.key == connector.key)).health = "down"
    report = dispatch_pending(ctx.session_factory, sink, at, eligibility=delivery_check(ctx.settings))
    assert report.sent == 0 and report.suppressed == 1 and not sink.sent


def test_cross_currency_uses_dated_reference_rates_without_fee_assumptions(now):
    from value_rail.valuation.models import FxRate
    offer = listing(now, currency="USD", unit_price=Decimal("95"))
    fx = FxRate(currency="USD", rate_to_eur="0.90", captured_at=now, quote_ref="TEST-ONLY ECB fixture")
    inp = RouteInputs(route_key="TEST-ONLY", product=PRODUCT, offers=[offer], fx_rates=[fx], evaluated_at=now)
    result = evaluate_route(inp, RULE)
    assert result.status == "price_find" and result.discount == Decimal("0.145")
    assert result.screening["currency"] == "USD" and result.screening["face_currency"] == "EUR"
    assert result.screening["fx_used"] and result.unit_all_in_eur == "unknown"
    assert evaluate_route(inp.model_copy(update={"fx_rates": [fx.model_copy(update={"captured_at": now - timedelta(days=5)})]}), RULE).status == "blocked"
    assert evaluate_route(inp.model_copy(update={"fx_rates": [fx.model_copy(update={"captured_at": now + timedelta(seconds=1)})]}), RULE).status == "blocked"


def test_ecb_parser_retains_publication_date_and_response_hash():
    from value_rail.worker.fx import parse_rates
    body = b'<Envelope><Cube><Cube time="2026-10-07"><Cube currency="USD" rate="1.25"/></Cube></Cube></Envelope>'
    fx = parse_rates(body)[0]
    assert fx.rate_to_eur == Decimal("0.8") and fx.captured_at.date().isoformat() == "2026-10-07"
    assert "sha256=" in fx.quote_ref
    with pytest.raises(ValueError):
        parse_rates(body.replace(b'1.25', b'0'))


def test_screener_dashboard_and_details_show_price_without_fee_or_payout_panels(ctx, now):
    from fastapi.testclient import TestClient
    from value_rail.web.app import create_app
    configure(ctx, now)
    report = run_scan(ctx.session_factory, SimulatedListing(), ctx.settings, now)
    client = TestClient(create_app(ctx))
    html = client.get("/").text
    assert "Arbitrage-Kandidaten (1)" in html and "Verifizierte Routen" not in html
    detail = client.get(f"/evaluations/{report.evaluation_ids['TEST-ONLY']}").text
    assert "Angebotspreis" in detail and "Angebot öffnen" in detail
    assert "Netto-Exit" not in detail and "All-in je Stück" not in detail and "Profit(q)" not in detail


def test_disabling_catalogue_filter_does_not_disable_freshness_at_dispatch(ctx, now):
    configure(ctx, now)
    ctx.settings.file_config.scope.enabled = False
    run_scan(ctx.session_factory, SimulatedListing(), ctx.settings, now)
    report = dispatch_pending(ctx.session_factory, MemorySink(), now + timedelta(seconds=3601), eligibility=delivery_check(ctx.settings))
    assert report.sent == 0 and report.suppressed == 1


def test_screener_skips_connector_checkout_and_exit_requests(ctx, now):
    configure(ctx, now)
    class NoCheckout(SimulatedListing):
        def capabilities(self):
            return super().capabilities().model_copy(update={"checkout_quote": True, "exit_quote": True})
        def checkout_quote(self, item, now):
            raise AssertionError("screener must not request a checkout")
        def exit_quote(self, item, now):
            raise AssertionError("screener must not request a payout")
    assert run_scan(ctx.session_factory, NoCheckout(), ctx.settings, now).alerts_enqueued == 1
