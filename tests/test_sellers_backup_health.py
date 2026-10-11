"""New-seller detection (through run_scan), backup/restore test, extended health JSON, scheduler wiring."""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import pytest
from sqlalchemy import select

from value_rail.backup import create_backup, list_backups, prune, restore_test, run_backup_job
from value_rail.health import compute_health
from value_rail.services import AppContext
from value_rail.settings import JobConfig
from value_rail.storage.orm import SellerOfferEventRow, SellerOfferRow
from value_rail.worker.scan import run_scan
from value_rail.worker.scheduler import Scheduler, effective_interval

from .conftest import NOW, FIXTURES, make_settings
from value_rail.connectors.fixture import FixtureConnector
def test_backup_restore_and_retention(ctx, tmp_path):
    rep = run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, NOW, trigger="test")
    info = create_backup(ctx.settings, now=NOW)
    assert info["counts"]["offer_snapshots"] == rep.offers_seen > 0 and info["counts"]["rule_versions"] >= 1
    rt = restore_test(info["backup"])
    assert rt["ok"] and rt["integrity_check"] == "ok" and rt["expected_counts"] == rt["restored_counts"]
    for i in range(1, 5):
        create_backup(ctx.settings, now=NOW + timedelta(days=i), keep=3)
    assert len(list_backups(ctx.settings.backup_dir)) == 3
    assert prune(ctx.settings.backup_dir, 1) and len(list_backups(ctx.settings.backup_dir)) == 1


def test_restore_test_detects_corruption(ctx):
    info = create_backup(ctx.settings, now=NOW)
    p = info["backup"]
    data = bytearray(open(p, "rb").read())
    data[100:4000] = b"\x00" * 3900
    open(p, "wb").write(bytes(data))
    rt = restore_test(p)
    assert rt["ok"] is False


def test_backup_job_writes_status_and_health_reports_it(ctx):
    info = run_backup_job(ctx.settings, now=NOW)
    assert info["ok"]
    with ctx.session_factory() as s:
        body, _ = compute_health(s, ctx.settings, NOW)
    assert body["backup"]["ok"] and body["backup"]["restore_ok"]
    assert body["alerts_open"] == {"pending": 0, "dead": 0}


def test_health_tracks_only_coingate_clearance(tmp_path, now):
    from pathlib import Path
    settings = make_settings(tmp_path, config_path=Path(__file__).resolve().parents[1] / "config/production.toml")
    ctx = AppContext(settings)
    try:
        ctx.init_db(now=now)
        with ctx.session_factory() as s:
            body, _ = compute_health(s, settings, now)
        assert [x["key"] for x in body["sources"]] == ["coingate"]
        assert body["stale_sources"] == ["coingate"]
        assert {j["name"] for j in body["jobs"]} == {"coingate_clearance", "backup_daily"}
        assert body["sources"][0]["max_age_s"] == settings.file_config.scheduler.stale_factor * 300
    finally:
        ctx.dispose()


def test_scheduler_passes_job_options_and_runs_backup(tmp_path):
    from .test_scheduler import Clock  # reuse
    prod = make_settings(tmp_path)
    ctx = AppContext(prod)
    ctx.init_db(now=NOW)
    seen = {}

    class Fake:
        key = "fixture"

        def configure_for_job(self, options):
            seen["options"] = options

        def capabilities(self):
            from value_rail.connectors.base import ConnectorCapabilities
            return ConnectorCapabilities(synthetic=True)

        def discovery(self, now):
            return []

    ctx.settings.file_config.jobs[:] = [JobConfig(name="j", connector="fixture", interval_seconds=10, enabled=True,
                                                  options={"tiers": ["watch"]}),
                                        JobConfig(name="b", kind="backup", interval_seconds=86400, enabled=True)]
    sch = Scheduler(ctx, owner="t", clock=Clock(NOW), connector_factory=lambda k: Fake(), dispatch=False)
    res = sch.tick()
    assert sorted(res["ran"]) == ["b", "j"] and seen["options"] == {"tiers": ["watch"]}
    assert list_backups(ctx.settings.backup_dir)
    assert effective_interval(ctx.settings.file_config.jobs[0]) == 60  # min_interval floor
    ctx.dispose()


def test_backup_is_single_file_without_wal_sidecars(ctx):
    info = create_backup(ctx.settings, now=NOW)
    restore_test(info["backup"])
    import os
    assert not os.path.exists(info["backup"] + "-wal") and not os.path.exists(info["backup"] + "-shm")
    con = sqlite3.connect(info["backup"])
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    con.close()
