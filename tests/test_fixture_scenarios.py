"""Data-driven: every SYNTHETIC scenario's `expected` block must hold after a full offline scan."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from value_rail.connectors.fixture import FixtureConnector
from value_rail.storage.orm import AlertRow, EvidenceRow, RouteEvaluationRow
from value_rail.worker.scan import run_scan

from .conftest import FIXTURES

SCENARIOS = sorted(p.stem for p in (FIXTURES / "scenarios").glob("*.json"))


def test_all_fixtures_marked_synthetic():
    for p in (FIXTURES / "scenarios").glob("*.json"):
        d = json.loads(p.read_text())
        assert d["synthetic"] is True and "SYNTHETIC" in d["_notice"]
        assert all("SYNTHETIC" in s["name"] for s in d["sources"])


@pytest.fixture
def scanned(ctx, now):
    rep = run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    return ctx, rep


def _eq(actual, expected):
    if isinstance(expected, str) and expected not in ("unknown",) and not expected.isalpha() and "_" not in expected:
        return Decimal(str(actual)) == Decimal(expected)
    return str(actual) == str(expected)


@pytest.mark.parametrize("sid", SCENARIOS)
def test_scenario_expectations(scanned, sid):
    ctx, rep = scanned
    exp = json.loads((FIXTURES / "scenarios" / f"{sid}.json").read_text())["expected"]
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow, rep.evaluation_ids[f"synthetic:{sid}"])
        out = ev.outputs
        alerts = list(s.scalars(select(AlertRow).where(AlertRow.route_key == ev.route_key)))
        assert ev.is_synthetic
    for k, v in exp.items():
        if k == "alert":
            assert bool(alerts) is v
        elif k == "block_reason":
            assert v in out["block_reasons"]
        else:
            assert _eq(out[k], v), f"{sid}.{k}: {out[k]!r} != {v!r}"


def test_scan_persists_evidence_and_never_alerts_non_hits(scanned):
    ctx, rep = scanned
    assert rep.status == "ok"
    with ctx.session_factory() as s:
        assert s.scalar(select(EvidenceRow).where(EvidenceRow.kind == "purchase_receipt")) is not None
        statuses = {a.payload["status"] for a in s.scalars(select(AlertRow))}
    assert statuses <= {"price_find", "verified_route"}
    assert rep.alerts_enqueued == sum(1 for st in rep.statuses.values() if st in ("price_find", "verified_route"))
