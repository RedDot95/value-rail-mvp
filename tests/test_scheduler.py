"""Delivery 3 basics: DB lease (no overlap), persistent job state, bounded catch-up, heartbeat, /healthz."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from value_rail.health import compute_health
from value_rail.storage.orm import JobStateRow
from value_rail.web.app import create_app
from value_rail.worker.scheduler import DbLease, Scheduler, enabled_jobs


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def sched_ctx(ctx, tmp_path):
    ctx.settings.heartbeat_file = str(tmp_path / "heartbeat.json")
    return ctx


def test_lease_exclusive_renew_expire_release(ctx, now):
    a = DbLease(ctx.session_factory, "scheduler", "A", ttl_seconds=60)
    b = DbLease(ctx.session_factory, "scheduler", "B", ttl_seconds=60)
    assert a.acquire(now) and not b.acquire(now)
    assert a.acquire(now + timedelta(seconds=10))  # re-entrant for the holder
    assert a.renew(now + timedelta(seconds=50))
    assert not b.acquire(now + timedelta(seconds=100))  # renewed until now+110
    assert b.acquire(now + timedelta(seconds=111))  # A crashed / did not renew -> lease expired
    assert not a.renew(now + timedelta(seconds=112))
    a.release()  # not the owner -> no effect
    assert b.holder().owner == "B"
    b.release()
    assert b.holder() is None


def test_only_enabled_jobs_with_enabled_connectors(sched_ctx):
    assert [j.name for j in enabled_jobs(sched_ctx)] == ["fixture_scan"]  # live recharge job off by default


def test_overlap_second_scheduler_stands_by(sched_ctx, now):
    clock = Clock(now)
    s1 = Scheduler(sched_ctx, owner="w1", clock=clock, dispatch=False)
    s2 = Scheduler(sched_ctx, owner="w2", clock=clock, dispatch=False)
    r1 = s1.tick()
    r2 = s2.tick()
    assert r1["lock_held"] and r1["ran"] == ["fixture_scan"]
    assert not r2["lock_held"] and r2["ran"] == [] and r2["standby_for"] == "w1"


def test_job_state_persists_across_restart(sched_ctx, now):
    clock = Clock(now)
    Scheduler(sched_ctx, owner="w1", clock=clock, dispatch=False).run_forever(max_ticks=1, sleep=lambda s: None)
    with sched_ctx.session_factory() as s:
        st = s.get(JobStateRow, "fixture_scan")
        assert st.runs_total == 1 and st.last_status == "ok" and st.last_success_at == now
        assert st.next_due_at == now + timedelta(seconds=300) and st.last_scan_run_id is not None
    # restart (new process/owner): lease was released by run_forever; nothing due yet
    clock.t = now + timedelta(seconds=10)
    assert Scheduler(sched_ctx, owner="w2", clock=clock, dispatch=False).tick()["ran"] == []
    clock.t = now + timedelta(seconds=301)
    # w2 still holds its lease from the previous tick -> it runs the due job
    assert Scheduler(sched_ctx, owner="w2", clock=clock, dispatch=False).tick()["ran"] == ["fixture_scan"]


def test_bounded_catch_up_after_downtime(sched_ctx, now):
    clock = Clock(now)
    sch = Scheduler(sched_ctx, owner="w1", clock=clock, dispatch=False)
    sch.tick()
    clock.t = now + timedelta(hours=3, seconds=300)  # 3 h down: 36 missed 5-minute slots
    res = sch.tick()
    assert res["ran"] == ["fixture_scan"]  # max_catchup_runs = 1 -> one run, no backlog storm
    assert res["skipped_catchup"]["fixture_scan"] == 36
    with sched_ctx.session_factory() as s:
        st = s.get(JobStateRow, "fixture_scan")
        assert st.runs_total == 2 and st.skipped_catchup_total == 36
        assert st.next_due_at == clock.t + timedelta(seconds=300)


def test_catch_up_budget_respected(sched_ctx, now):
    sched_ctx.settings.file_config.scheduler.max_catchup_runs = 3
    clock = Clock(now)
    sch = Scheduler(sched_ctx, owner="w1", clock=clock, dispatch=False)
    sch.tick()
    clock.t = now + timedelta(hours=1, seconds=300)
    res = sch.tick()
    assert res["ran"] == ["fixture_scan"] * 3 and res["skipped_catchup"]["fixture_scan"] == 13 - 3


def test_failing_job_recorded_and_health_turns_stale(sched_ctx, now):
    clock = Clock(now)

    def boom(key):
        raise RuntimeError("connector exploded")

    sch = Scheduler(sched_ctx, owner="w1", clock=clock, connector_factory=boom, dispatch=False)
    sch.tick()
    with sched_ctx.session_factory() as s:
        st = s.get(JobStateRow, "fixture_scan")
        assert st.last_status == "failed" and st.consecutive_failures == 1 and "exploded" in st.last_error
        body, code = compute_health(s, sched_ctx.settings, now + timedelta(seconds=60))
        assert body["status"] == "failing" and code == 503  # ran but never succeeded
    # a later success turns it ok; a long gap afterwards turns it stale
    sch.connector_factory = sch._build_connector
    clock.t = now + timedelta(seconds=300)
    sch.tick()
    with sched_ctx.session_factory() as s:
        assert compute_health(s, sched_ctx.settings, clock.t)[0]["status"] == "ok"
        body, code = compute_health(s, sched_ctx.settings, clock.t + timedelta(seconds=901))
        assert body["status"] == "stale" and code == 503


def test_fresh_install_is_starting_not_alarm(sched_ctx, now):
    from value_rail.worker.scheduler import sync_job_states
    sync_job_states(sched_ctx, now)
    with sched_ctx.session_factory() as s:
        body, code = compute_health(s, sched_ctx.settings, now + timedelta(seconds=30))
    assert body["status"] == "starting" and code == 200


def test_heartbeat_file_and_healthz_endpoint(sched_ctx, now, monkeypatch):
    clock = Clock(now)
    Scheduler(sched_ctx, owner="w1", clock=clock, dispatch=False).tick()
    hb = json.loads(open(sched_ctx.settings.heartbeat_file).read())
    assert hb["lock_held"] is True and hb["jobs"]["fixture_scan"]["last_status"] == "ok"
    assert hb["written_at"].startswith("2026-10-04T12:00")

    monkeypatch.setattr("value_rail.web.app.utcnow", lambda: now + timedelta(seconds=30))
    c = TestClient(create_app(sched_ctx))
    r = c.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["heartbeat"]["present"] is True
    job = body["jobs"][0]
    assert job["name"] == "fixture_scan" and job["last_success_berlin"].startswith("04.10.2026 14:00:00")
    monkeypatch.setattr("value_rail.web.app.utcnow", lambda: now + timedelta(hours=2))
    assert c.get("/healthz").status_code == 503
    assert c.get("/livez").status_code == 200
