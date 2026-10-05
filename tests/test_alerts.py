"""Alert outbox, dedup, material change, restart/retry (cases 12, 13, 14)."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from sqlalchemy import func, select

from value_rail.alerts.dispatcher import dispatch_pending
from value_rail.alerts.sinks import LogAlertSink, MemorySink
from value_rail.connectors.fixture import FixtureConnector
from value_rail.services import AppContext
from value_rail.storage.orm import AlertRow, RouteEvaluationRow
from value_rail.worker.scan import run_scan

from .conftest import FIXTURES, load_scenario, write_scenario


def _alerts(ctx):
    with ctx.session_factory() as s:
        return list(s.scalars(select(AlertRow).order_by(AlertRow.id)))


# 12
def test_case12_identical_rescan_no_duplicate_alert(ctx, now, tmp_path, caplog):
    sink = LogAlertSink(tmp_path / "alerts.jsonl")
    caplog.set_level(logging.INFO, logger="value_rail.alerts")
    r1 = run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    d1 = dispatch_pending(ctx.session_factory, sink, now)
    r2 = run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now + timedelta(minutes=5))
    d2 = dispatch_pending(ctx.session_factory, sink, now + timedelta(minutes=5))
    assert r1.alerts_enqueued == 5 and d1.sent == 5
    assert r2.alerts_enqueued == 0 and d2.attempted == 0
    lines = (tmp_path / "alerts.jsonl").read_text().splitlines()
    assert len(lines) == 5
    payloads = [json.loads(x) for x in lines]
    assert len({p["event_id"] for p in payloads}) == 5
    assert all(p["synthetic"] is True and p["type"] == "value_rail.alert" for p in payloads)
    assert sum('"type": "value_rail.alert"' in r.getMessage() for r in caplog.records) == 5
    with ctx.session_factory() as s:  # evaluations are still recorded for every scan (audit)
        assert s.scalar(select(func.count()).select_from(RouteEvaluationRow)) == 20


# 13
def test_case13_restock_and_material_price_change_create_new_events(tmp_path, scenario_dir, now):
    from .conftest import make_settings
    ctx = AppContext(make_settings(tmp_path, fixtures_dir=scenario_dir))
    ctx.init_db(now=now)
    base = load_scenario("R02_bitsa_price_find")
    # keep only one scenario to make counting obvious
    for p in (scenario_dir / "scenarios").glob("*.json"):
        p.unlink()
    sc = json.loads(json.dumps(base))
    sc["offers"][0]["advertised_quantity"]["value"] = 0
    write_scenario(scenario_dir, sc)

    def scan(t):
        return run_scan(ctx.session_factory, FixtureConnector(scenario_dir), ctx.settings, t)

    assert scan(now).alerts_enqueued == 1                      # first sighting
    assert scan(now + timedelta(minutes=5)).alerts_enqueued == 0  # identical
    sc["offers"][0]["advertised_quantity"]["value"] = 50
    write_scenario(scenario_dir, sc)
    assert scan(now + timedelta(minutes=10)).alerts_enqueued == 1  # restock 0 -> 50
    sc["offers"][0]["price_text"] = "1,21 €"                  # +0.83 % -> immaterial (< 2 %)
    write_scenario(scenario_dir, sc)
    assert scan(now + timedelta(minutes=15)).alerts_enqueued == 0
    sc["offers"][0]["price_text"] = "1,10 €"                  # -8.3 % vs last alert -> material
    write_scenario(scenario_dir, sc)
    assert scan(now + timedelta(minutes=20)).alerts_enqueued == 1
    reasons = [a.reason for a in _alerts(ctx)]
    assert reasons == ["new", "restock", "material_price_change"]
    sc["offers"][0]["advertised_quantity"]["value"] = 40      # quantity decrease -> no event
    write_scenario(scenario_dir, sc)
    assert scan(now + timedelta(minutes=25)).alerts_enqueued == 0
    ctx.dispose()


def test_status_change_creates_event_and_event_ids_are_stable(tmp_path, scenario_dir, now):
    from value_rail.alerts.policy import make_event_id
    assert make_event_id("k", {"a": 1}, None) == make_event_id("k", {"a": 1}, None)
    assert make_event_id("k", {"a": 1}, "prev") != make_event_id("k", {"a": 1}, None)


# 14
def test_case14_restart_between_evaluation_and_send_keeps_outbox(tmp_path, now):
    from .conftest import make_settings
    st = make_settings(tmp_path)
    ctx1 = AppContext(st)
    ctx1.init_db(now=now)
    rep = run_scan(ctx1.session_factory, FixtureConnector(FIXTURES), st, now)
    assert rep.alerts_enqueued == 5
    ctx1.dispose()  # "crash/restart" before dispatch

    ctx2 = AppContext(make_settings(tmp_path))  # fresh process view of the same DB file
    pending = [a for a in _alerts(ctx2) if a.state == "pending"]
    assert len(pending) == 5
    sink = MemorySink(fail_times=1)
    d1 = dispatch_pending(ctx2.session_factory, sink, now, backoff_seconds=60)
    assert (d1.attempted, d1.sent, d1.failed) == (5, 4, 1)
    failed = [a for a in _alerts(ctx2) if a.state == "pending"]
    assert len(failed) == 1 and failed[0].attempts == 1 and "simulated sink failure" in failed[0].last_error
    assert failed[0].next_attempt_at == now + timedelta(seconds=60)
    assert dispatch_pending(ctx2.session_factory, sink, now + timedelta(seconds=30)).attempted == 0  # backoff
    d3 = dispatch_pending(ctx2.session_factory, sink, now + timedelta(seconds=61))
    assert d3.sent == 1
    final = _alerts(ctx2)
    assert all(a.state == "sent" for a in final)
    assert [a.attempts for a in final if a.id == failed[0].id] == [2]
    assert len(sink.sent) == 5 and len({p["event_id"] for p in sink.sent}) == 5
    ctx2.dispose()


def test_retries_are_limited_then_dead(ctx, now):
    run_scan(ctx.session_factory, FixtureConnector(FIXTURES, only={"R02_bitsa_price_find"}), ctx.settings, now)
    sink = MemorySink(fail_times=999)
    t = now
    for _ in range(10):
        dispatch_pending(ctx.session_factory, sink, t, backoff_seconds=1)
        t += timedelta(hours=1)
    (a,) = _alerts(ctx)
    assert a.state == "dead" and a.attempts == a.max_attempts == 5
