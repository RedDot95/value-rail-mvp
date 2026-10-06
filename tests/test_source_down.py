"""Case 15: source down = disturbance, not 'no deals'; existing data marked stale."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from value_rail.connectors.fixture import FixtureConnector
from value_rail.storage.orm import ScanRunRow, SourceRow
from value_rail.web.views import dashboard

from .conftest import FIXTURES


def test_case15_source_down_is_disturbance_and_marks_stale(ctx, now):
    from value_rail.worker.scan import run_scan
    ok = run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    assert ok.status == "ok"
    later = now + timedelta(minutes=5)
    rep = run_scan(ctx.session_factory, FixtureConnector(FIXTURES, down_sources={"synthetic-bitsa-reseller"}),
                   ctx.settings, later)
    assert rep.status == "degraded"
    assert "synthetic-bitsa-reseller" in rep.sources_failed
    assert "synthetic:R02_bitsa_price_find" not in rep.statuses  # not evaluated -> no "0 deals" claim
    with ctx.session_factory() as s:
        src = s.scalar(select(SourceRow).where(SourceRow.key == "synthetic-bitsa-reseller"))
        assert src.health == "down" and "simulated outage" in src.last_error
        scan = s.get(ScanRunRow, rep.scan_run_id)
        assert scan.status == "degraded" and scan.sources_failed
        vm = dashboard(s, ctx.settings, later)
    assert vm["system"]["level"] == "bad"
    assert "Störung" in vm["system"]["headline"] and "keine Deals" in vm["system"]["headline"]
    bitsa = [c for c in vm["groups"]["price_find"] if c["route_key"] == "synthetic:R02_bitsa_price_find"]
    assert bitsa and bitsa[0]["stale"] and "Quelle gestört" in bitsa[0]["stale_reasons"][0]


def test_old_data_marked_stale_by_age(ctx, now):
    from value_rail.worker.scan import run_scan
    run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    with ctx.session_factory() as s:
        vm = dashboard(s, ctx.settings, now + timedelta(hours=1))
    assert vm["system"]["level"] in ("warn", "bad") and "veraltet" in vm["system"]["headline"]
    assert all(c["stale"] for g in vm["groups"].values() for c in g)


@pytest.mark.parametrize("failed_first", [True, False])
def test_partial_source_failure_is_down_regardless_of_item_order(ctx, now, failed_first):
    from value_rail.connectors.base import SourceUnavailable
    from value_rail.worker.scan import run_scan

    shared = "synthetic-direct-a"

    class OrderedFailure(FixtureConnector):
        def discovery(self, at):
            found = super().discovery(at)
            return sorted(found, key=lambda i: i.meta["scenario_id"] != "R04_verified_profit_55",
                          reverse=not failed_first)

        def offer_fetch(self, item, at):
            if item.meta["scenario_id"] == "R04_verified_profit_55":
                raise SourceUnavailable(shared, "one product page failed")
            return super().offer_fetch(item, at)

    run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    rep = run_scan(ctx.session_factory, OrderedFailure(FIXTURES), ctx.settings, now + timedelta(minutes=5))
    assert rep.status == "degraded" and shared in rep.sources_failed
    with ctx.session_factory() as s:
        src = s.scalar(select(SourceRow).where(SourceRow.key == shared))
        assert src.health == "down"
        assert src.last_success_at == now
        assert "one product page failed" in src.last_error


def test_discovery_failure_marks_existing_source_down(ctx, now):
    from value_rail.connectors.base import SourceUnavailable
    from value_rail.worker.scan import run_scan

    run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)

    class DiscoveryFailure(FixtureConnector):
        def discovery(self, at):
            raise SourceUnavailable("synthetic-bitsa-reseller", "discovery unavailable")

    rep = run_scan(ctx.session_factory, DiscoveryFailure(FIXTURES), ctx.settings, now + timedelta(minutes=5))
    assert rep.status == "failed"
    with ctx.session_factory() as s:
        src = s.scalar(select(SourceRow).where(SourceRow.key == "synthetic-bitsa-reseller"))
        assert src.health == "down" and src.last_success_at == now
