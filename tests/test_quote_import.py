"""Entirely simulated quote documents; never real provider quotes or profits."""
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from value_rail.connectors.fixture import FixtureConnector
from value_rail.quote_import import import_quotes
from value_rail.settings import OperatorConfig, OperatorProof
from value_rail.storage.orm import EvidenceRow, RouteEvaluationRow
from value_rail.valuation.replay import replay_evaluation
from value_rail.worker.scan import run_scan

from .conftest import FIXTURES, REPO, make_settings


@pytest.fixture
def manifest(ctx, now, tmp_path):
    class TestProvider(FixtureConnector):
        def capabilities(self):
            return super().capabilities().model_copy(update={"synthetic": False})
        def discovery(self, at):
            return [i.model_copy(update={"is_synthetic": False, "product_family": "amazon"})
                    for i in super().discovery(at)]
    ctx.settings.file_config.operator = OperatorConfig(name="TEST-ONLY reviewer", capabilities={
        n: OperatorProof(status="proven", evidence_ref="TEST-ONLY account proof")
        for n in ("synthetic_seller_account", "synthetic_exit_account")})
    ctx.settings.file_config.scope.enabled = True
    ctx.seed(now=now)
    report = run_scan(ctx.session_factory, TestProvider(FIXTURES, only={"R04_verified_profit_55"}), ctx.settings, now)
    ev_id = next(iter(report.evaluation_ids.values()))
    with ctx.session_factory() as s:
        identity = s.get(RouteEvaluationRow, ev_id).inputs["product"]
    artifact = tmp_path / "TEST-ONLY.txt"
    artifact.write_text("SYNTHETIC TEST DOCUMENT: not a real market quote")
    q = {"identity": identity, "source_url": "https://seller.invalid/test-quote", "source_name": "TEST-ONLY",
         "unit_price": "45", "currency": "EUR", "quantity": 3, "captured_at": now.isoformat(),
         "valid_until": (now + timedelta(minutes=10)).isoformat(), "firm": True, "fees_complete": True,
         "fees": [], "artifact": artifact.name, "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
    document = {"schema_version": 1, "evaluation_id": ev_id, "reviewed_by": "TEST-ONLY reviewer", "checkout": q,
                "exit": q | {"source_url": "https://buyer.invalid/test-quote", "unit_price": "100", "quantity": 2}}
    path = tmp_path / "quotes.json"
    path.write_text(json.dumps(document))
    return path, document


def test_import_binds_artifacts_preserves_original_and_limits_exit_depth(ctx, now, manifest):
    path, doc = manifest
    with ctx.session_factory() as s:
        original = s.get(RouteEvaluationRow, doc["evaluation_id"]).inputs
    report = import_quotes(ctx, path, now)
    assert report["status"] == "verified_route" and report["profit_eur"] == "110"
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow, report["evaluation_id"])
        assert ev.evaluated_quantity == "2"
        assert datetime.fromisoformat(ev.inputs["checkout_quote"]["captured_at"]) == now
        assert ev.route_key.startswith("reviewed:")
        assert s.get(RouteEvaluationRow, doc["evaluation_id"]).inputs == original
        assert replay_evaluation(s, ev.id).match
        evidence = list(s.scalars(select(EvidenceRow).where(EvidenceRow.scope == "operator-reviewed")))
        assert len(evidence) == 3 and all(e.payload["artifact_sha256"] == doc["checkout"]["artifact_sha256"] for e in evidence)


@pytest.mark.parametrize("failure", ["tampered", "escape", "future", "naive", "wrong_identity", "indicative",
                                     "fees_incomplete", "negative_fee", "reviewer", "synthetic", "old_base"])
def test_invalid_import_is_atomic_and_cannot_promote_unsupported_evidence(ctx, now, manifest, failure):
    path, doc = manifest
    q = doc["checkout"]
    if failure == "tampered":
        (path.parent / q["artifact"]).write_text("changed")
    elif failure == "escape":
        q["artifact"] = "../outside.txt"
    elif failure == "future":
        q["captured_at"] = (now + timedelta(seconds=1)).isoformat()
    elif failure == "naive":
        q["captured_at"] = now.replace(tzinfo=None).isoformat()
    elif failure == "wrong_identity":
        q["identity"] = q["identity"] | {"region": "US"}
    elif failure == "indicative":
        q["firm"] = False
    elif failure == "fees_incomplete":
        q["fees_complete"] = False
    elif failure == "negative_fee":
        q["fees"] = [{"name": "fake", "kind": "fixed_per_order", "amount": "-100"}]
    elif failure == "reviewer":
        doc["reviewed_by"] = "SYNTHETIC operator"
    elif failure == "synthetic":
        rep = run_scan(ctx.session_factory, FixtureConnector(FIXTURES, only={"R04_verified_profit_55"}), ctx.settings, now)
        doc["evaluation_id"] = next(iter(rep.evaluation_ids.values()))
    else:
        with ctx.session_factory.begin() as s:
            base = s.get(RouteEvaluationRow, doc["evaluation_id"])
            vals = {col.name: getattr(base, col.name) for col in RouteEvaluationRow.__table__.columns if col.name != "id"}
            vals["evaluated_at"] = now + timedelta(seconds=1)
            s.add(RouteEvaluationRow(**vals))
    path.write_text(json.dumps(doc))
    with ctx.session_factory() as s:
        before = s.scalar(select(func.count()).select_from(RouteEvaluationRow))
    with pytest.raises((ValueError, OSError)):
        import_quotes(ctx, path, now)
    with ctx.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(RouteEvaluationRow)) == before


def test_old_capture_is_not_refreshed_and_unknown_fees_stay_blocking(ctx, now, manifest):
    path, doc = manifest
    report = import_quotes(ctx, path, now + timedelta(hours=1))
    assert report["status"] == "expired" and not report["alert_enqueued"]
    doc["evaluation_id"] = report["evaluation_id"]
    doc["checkout"]["fees"] = [{"name": "payment_fee", "kind": "fixed_per_order", "amount": "unknown"}]
    path.write_text(json.dumps(doc))
    report = import_quotes(ctx, path, now + timedelta(hours=1))
    assert report["status"] == "blocked" and "unknown_required_fee:payment_fee" in report["block_reasons"]


def test_cli_template_is_incomplete_and_rejection_does_not_echo_input(ctx, manifest, monkeypatch):
    from typer.testing import CliRunner
    from value_rail.cli import app
    path, doc = manifest
    monkeypatch.setattr("value_rail.cli._ctx", lambda: ctx)
    runner = CliRunner()
    result = runner.invoke(app, ["quote-template", str(doc["evaluation_id"])])
    template = json.loads(result.stdout)
    assert result.exit_code == 0 and not template["checkout"]["firm"]
    assert template["checkout"]["identity"] == doc["checkout"]["identity"]
    doc["checkout"]["firm"] = False
    doc["checkout"]["source_name"] = "PRIVATE-INPUT-MUST-NOT-BE-ECHOED"
    path.write_text(json.dumps(doc))
    rejected = runner.invoke(app, ["import-quotes", str(path)])
    assert rejected.exit_code == 2 and "PRIVATE-INPUT-MUST-NOT-BE-ECHOED" not in rejected.output


@pytest.mark.parametrize("change", ["revoke", "remove"])
def test_revoked_operator_proof_suppresses_old_verified_quote_and_coverage(ctx, now, manifest, change):
    from value_rail.alerts.dispatcher import dispatch_pending
    from value_rail.alerts.eligibility import delivery_check
    from value_rail.alerts.sinks import MemorySink
    from value_rail.coverage import coverage_report
    path, _ = manifest
    report = import_quotes(ctx, path, now)
    assert report["status"] == "verified_route"
    if change == "revoke":
        ctx.settings.file_config.operator.capabilities["synthetic_exit_account"] = OperatorProof(status="unknown")
    else:
        ctx.settings.file_config.operator = None
    ctx.seed(now=now)
    with ctx.session_factory() as s:
        coverage = coverage_report(s, ctx.settings, now)
        assert coverage["verified_routes_now"] == []
        assert s.get(RouteEvaluationRow, report["evaluation_id"]).status == "verified_route"  # history unchanged
    sent = dispatch_pending(ctx.session_factory, MemorySink(), now, eligibility=delivery_check(ctx.settings))
    assert sent.sent == 0 and sent.suppressed >= 1


def test_production_has_no_automatic_refund_fee_models(tmp_path):
    params = make_settings(tmp_path, config_path=REPO / "config/production.toml").file_config.rules
    assert params.evaluation_mode == "screener"
    assert params.exit_rules == []
