from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from value_rail.catalog import instruments, resolve_instrument
from value_rail.connectors.base import SourceSpec
from value_rail.connectors.fixture import FixtureConnector
from value_rail.coverage import coverage_report
from value_rail.settings import OperatorConfig, OperatorProof
from value_rail.storage.orm import OperatorProfileRow, RouteEvaluationRow, SourceRow
from value_rail.worker.scan import run_scan

from .conftest import FIXTURES, REPO


@pytest.mark.parametrize("name,key", [
    ("A-bon EU - 50 EUR", "abon"), ("Aircash Voucher", "aircash"), ("PCS Recharge Euro Area", "pcs"),
    ("Crypto Voucher 100 EUR", "cryptovoucher"), ("Flexepin EUR 50", "flexepin"),
    ("Rewarble PayPal Global - 10 USD", "rewarble-paypal"), ("PayPal gift card", "paypal-unverified"),
    ("Media Markt Germany", "mediamarkt"), ("Amazon DE", "amazon"), ("Otto", "otto"),
    ("C&A gift card", "ca"), ("H&M", "hm")])
def test_catalogue_classifies_user_scope(name, key):
    assert resolve_instrument(name)["key"] == key


@pytest.mark.parametrize("name", ["Steam", "Netflix", "PlayStation Network", "Xbox", "Google Play",
                                  "Spotify", "Roblox", "Rewarble Fansly", "Steam card Amazon", "unrecognised brand"])
def test_games_streaming_and_unknown_products_are_not_eligible(name):
    assert resolve_instrument(name) is None


def test_catalogue_never_asserts_liquidity_and_keys_are_unique():
    rows = instruments()
    assert len(rows) >= 70 and len({r["key"] for r in rows}) == len(rows)
    assert all(r["liquidity"] == "unproven" for r in rows)


class RealFixture(FixtureConnector):
    """Test-only simulated real connector, NEVER an actual market observation."""
    def capabilities(self):
        return super().capabilities().model_copy(update={"synthetic": False})

    def discovery(self, at):
        return [i.model_copy(update={"is_synthetic": False}) for i in super().discovery(at)]


def test_real_scan_cannot_borrow_synthetic_operator_prerequisites(ctx, now):
    rep = run_scan(ctx.session_factory, RealFixture(FIXTURES, only={"R04_verified_profit_55"}), ctx.settings, now)
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow, next(iter(rep.evaluation_ids.values())))
    assert ev.operator_profile_id is None and ev.status != "verified_route"
    assert all(p["status"] == "unknown" for p in ev.inputs["prerequisites"])
    assert rep.alerts_enqueued == 1  # offline default still permits diagnostic price finds


def test_real_operator_requires_evidence_and_does_not_affect_fixture_operator(ctx, now):
    with pytest.raises(ValidationError, match="evidence_ref"):
        OperatorProof(status="proven")
    ctx.settings.file_config.operator = OperatorConfig(name="real-operator", capabilities={
        "synthetic_seller_account": OperatorProof(status="proven", evidence_ref="TEST-ONLY seller evidence"),
        "synthetic_exit_account": OperatorProof(status="proven", evidence_ref="TEST-ONLY exit evidence")})
    ctx.seed(now=now)
    rep = run_scan(ctx.session_factory, RealFixture(FIXTURES, only={"R04_verified_profit_55"}), ctx.settings, now)
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow, next(iter(rep.evaluation_ids.values())))
        operator = s.get(OperatorProfileRow, ev.operator_profile_id)
    assert operator.name == "real-operator" and not operator.is_synthetic
    assert ev.status == "verified_route"
    assert all(p["evidence_ref"].startswith("TEST-ONLY") for p in ev.inputs["prerequisites"])
    rep = run_scan(ctx.session_factory, FixtureConnector(FIXTURES, only={"R04_verified_profit_55"}), ctx.settings, now)
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow, next(iter(rep.evaluation_ids.values())))
        assert s.get(OperatorProfileRow, ev.operator_profile_id).is_synthetic


def test_scope_skips_games_but_records_page_disturbances(ctx, now):
    class Game(RealFixture):
        def discovery(self, at):
            items = super().discovery(at)
            return [i.model_copy(update={"product_family": "steam", "product": i.product.model_copy(
                update={"redemption_program": "steam"})}) for i in items]
    ctx.settings.file_config.scope.enabled = True
    rep = run_scan(ctx.session_factory, Game(FIXTURES, only={"R04_verified_profit_55"}), ctx.settings, now)
    assert rep.items_out_of_scope == 1 and rep.evaluations_created == 0 and rep.alerts_enqueued == 0


def test_proven_empty_page_updates_source_health(ctx, now):
    class Empty(RealFixture):
        source = SourceSpec(key="empty-test", name="TEST ONLY", kind="aggregator", role="discovery_only")
        ok_pages = {"https://test.invalid/empty"}
        def discovery(self, at):
            return []
    rep = run_scan(ctx.session_factory, Empty(FIXTURES), ctx.settings, now)
    assert rep.status == "ok"
    with ctx.session_factory() as s:
        source = s.scalar(select(SourceRow).where(SourceRow.key == "empty-test"))
        assert source.health == "ok" and source.last_success_at == now


def test_production_alerts_candidates_and_targets_liquid_families(tmp_path):
    from .conftest import make_settings
    settings = make_settings(tmp_path, config_path=REPO / "config/production.toml")
    assert settings.file_config.scope.enabled
    assert settings.file_config.alerts.alert_statuses == ["price_find"]
    assert settings.file_config.rules.evaluation_mode == "screener"
    assert settings.file_config.rules.exit_rules == []
    assert settings.file_config.rules.price_find_min_discount == Decimal("0.01")
    bsv = next(c for c in settings.file_config.connectors if c.key == "buysellvouchers")
    assert {"abon", "pcs", "transcash", "cashlib", "flexepin", "amazon", "otto", "mediamarkt"} <= \
        {p["family"] for p in bsv.options["pages"]}
    cardbear = next(c for c in settings.file_config.connectors if c.key == "cardbear")
    assert [p["family"] for p in cardbear.options["pages"]] == ["amazon"]


def test_coverage_does_not_promote_synthetic_routes_to_real_signals(ctx, now):
    run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    with ctx.session_factory() as s:
        report = coverage_report(s, ctx.settings, now + timedelta(seconds=1))
    assert report["candidate_count"] >= 70 and report["verified_routes_now"] == []
    assert not report["real_operator_configured"]


@pytest.mark.parametrize("missing", ["offer", "checkout", "exit", "prerequisite", "fee", "fx"])
def test_real_economics_need_traceable_evidence(missing):
    from value_rail.valuation.engine import evaluate_route
    from value_rail.valuation.models import FxRate, Prerequisite
    from .conftest import RULE, NOW, checkout, exit_quote, fee, inputs, offer
    # Entirely simulated values; test provenance validation, never actual market data.
    o = offer().model_copy(update={"evidence_refs": ["TEST offer"]})
    cq = checkout().model_copy(update={"evidence_refs": ["TEST checkout"]})
    eq = exit_quote().model_copy(update={"evidence_refs": ["TEST exit"]})
    prereqs = [Prerequisite(name="test-account", status="proven", evidence_ref="TEST account")]
    fx = []
    if missing == "offer":
        o = o.model_copy(update={"evidence_refs": []})
    elif missing == "checkout":
        cq = cq.model_copy(update={"evidence_refs": []})
    elif missing == "exit":
        eq = eq.model_copy(update={"evidence_refs": []})
    elif missing == "prerequisite":
        prereqs = [prereqs[0].model_copy(update={"evidence_ref": "unknown"})]
    elif missing == "fee":
        cq = cq.model_copy(update={"fees": [fee("test-fee", "fixed_per_order", "1")]})
    else:
        cq = cq.model_copy(update={"currency": "USD"})
        fx = [FxRate(currency="USD", rate_to_eur="1", captured_at=NOW)]
    inp = inputs(offers=[o], cq=cq, eq=eq).model_copy(update={
        "is_synthetic": False, "prerequisites": prereqs, "fx_rates": fx})
    result = evaluate_route(inp, RULE)
    assert result.status != "verified_route"
    assert any("evidence" in x or x == "no_offer_matching_identity"
               for x in result.missing_evidence + result.block_reasons)


@pytest.mark.parametrize("failure", [None, "expired", "source_down", "game", "synthetic", "price_only", "latest_unprofitable"])
def test_verified_only_delivery_rechecks_pending_route(ctx, now, failure):
    from value_rail.alerts.dispatcher import dispatch_pending
    from value_rail.alerts.eligibility import delivery_check
    from value_rail.alerts.sinks import MemorySink
    from value_rail.storage.orm import AlertRow
    class Liquid(RealFixture):
        def discovery(self, at):
            return [i.model_copy(update={"product_family": "steam" if failure == "game" else "amazon"})
                    for i in super().discovery(at)]
    ctx.settings.file_config.operator = OperatorConfig(name="TEST-ONLY-operator", capabilities={
        "synthetic_seller_account": OperatorProof(status="proven", evidence_ref="TEST-ONLY seller proof"),
        "synthetic_exit_account": OperatorProof(status="proven", evidence_ref="TEST-ONLY exit proof")})
    ctx.seed(now=now)
    rep = run_scan(ctx.session_factory, Liquid(FIXTURES, only={"R04_verified_profit_55"}), ctx.settings, now)
    ctx.settings.file_config.scope.enabled = True
    ctx.settings.file_config.alerts.alert_statuses = ["verified_route"]
    with ctx.session_factory.begin() as s:
        # Entire connector and operator are test doubles; no market observation is asserted.
        ev = s.get(RouteEvaluationRow, next(iter(rep.evaluation_ids.values())))
        alert = s.scalar(select(AlertRow))
        alert.is_synthetic = failure == "synthetic"
        if failure == "price_only":
            alert.payload = alert.payload | {"status": "price_find"}
        if failure == "source_down":
            s.scalar(select(SourceRow).where(SourceRow.key == "synthetic-exit-venue")).health = "down"
        if failure == "latest_unprofitable":
            vals = {col.name: getattr(ev, col.name) for col in RouteEvaluationRow.__table__.columns if col.name != "id"}
            vals["evaluated_at"] = now + timedelta(seconds=1)
            vals["inputs"] = ev.inputs | {"exit_quote": ev.inputs["exit_quote"] | {"unit_price": "1"}}
            s.add(RouteEvaluationRow(**vals))
    sink = MemorySink()
    at = now + timedelta(hours=1) if failure == "expired" else now + timedelta(seconds=2)
    report = dispatch_pending(ctx.session_factory, sink, at, eligibility=delivery_check(ctx.settings))
    assert report.sent == int(failure is None)
    assert report.suppressed == int(failure is not None)
    if failure == "expired":
        refreshed = run_scan(ctx.session_factory, Liquid(FIXTURES, only={"R04_verified_profit_55"}), ctx.settings, at)
        assert refreshed.alerts_enqueued == 1
        assert dispatch_pending(ctx.session_factory, sink, at, eligibility=delivery_check(ctx.settings)).sent == 1
