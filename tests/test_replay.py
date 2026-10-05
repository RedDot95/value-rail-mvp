"""Case 16: historical rule change - old evaluation exactly reproducible."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from value_rail.connectors.fixture import FixtureConnector
from value_rail.storage.orm import RouteEvaluationRow
from value_rail.storage.repo import active_rule_version, add_rule_version, rule_params_of
from value_rail.valuation.replay import replay_evaluation
from value_rail.worker.scan import run_scan

from .conftest import load_scenario, write_scenario


def test_case16_rule_change_old_evaluation_reproducible(ctx, scenario_dir, now):
    # SYNTHETIC 27 % discount: Preisfund under v1 (25 %), not under v2 (30 %)
    sc = load_scenario("R02_bitsa_price_find")
    sc["scenario_id"] = "R16_rule_change"
    sc["offers"][0]["price_text"] = "3,65 €"
    for p in (scenario_dir / "scenarios").glob("*.json"):
        p.unlink()
    write_scenario(scenario_dir, sc)
    conn = FixtureConnector(scenario_dir)

    r1 = run_scan(ctx.session_factory, conn, ctx.settings, now)
    ev1 = r1.evaluation_ids["synthetic:R16_rule_change"]
    assert r1.statuses["synthetic:R16_rule_change"] == "price_find"

    t2 = now + timedelta(hours=1)
    with ctx.session_factory.begin() as s:
        v1 = active_rule_version(s, t2)
        p2 = rule_params_of(v1).model_copy(update={"label": "test-v2", "price_find_min_discount": Decimal("0.30")})
        add_rule_version(s, p2, valid_from=t2, now=t2, notes="SYNTHETIC rule change")
    r2 = run_scan(ctx.session_factory, FixtureConnector(scenario_dir), ctx.settings, t2 + timedelta(seconds=1))
    assert r2.statuses["synthetic:R16_rule_change"] == "no_signal"

    with ctx.session_factory() as s:
        res = replay_evaluation(s, ev1)
        stored = s.get(RouteEvaluationRow, ev1)
        assert res.match and res.diff == {} and res.inputs_hash_ok
        assert res.rule_label == "delivery2-2026-10-05-v2"
        assert stored.outputs["status"] == "price_find"
        res2 = replay_evaluation(s, r2.evaluation_ids["synthetic:R16_rule_change"])
        assert res2.match and res2.rule_label == "test-v2"
        # canonical JSON is byte-identical on replay
        from value_rail.valuation.engine import evaluate_route
        from value_rail.valuation.models import RouteInputs, RuleParams
        from value_rail.storage.orm import RuleVersionRow
        again = evaluate_route(RouteInputs.model_validate(stored.inputs),
                               RuleParams.model_validate(s.get(RuleVersionRow, stored.rule_version_id).params))
        assert json.dumps(again.canonical(), sort_keys=True) == json.dumps(stored.outputs, sort_keys=True)


def test_replay_all_fixture_evaluations(ctx, now):
    from .conftest import FIXTURES
    rep = run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    with ctx.session_factory() as s:
        for ev_id in rep.evaluation_ids.values():
            assert replay_evaluation(s, ev_id).match
