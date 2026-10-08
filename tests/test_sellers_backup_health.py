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

from .conftest import NOW, make_settings
from .test_jsonld_shop import GAMIVO, make, routes_for

URL = "https://www.gamivo.com/product/flexepin-eur-50"


def _gamivo(routes):
    c, _, _ = make("gamivo", GAMIVO, routes=routes)
    c.config.pages = [p for p in c.config.pages if p.path.endswith("flexepin-eur-50")]
    return c


def _body_with(extra_seller: str | None, drop: str | None = None, price_bump: str | None = None) -> bytes:
    import re
    html = (GAMIVO / "flexepin-eur-50.html").read_text()
    m = re.search(r'(<script[^>]*ld\+json[^>]*>)(.*?)(</script>)', html, re.S)
    graph = json.loads(m.group(2))
    prod = next(n for n in graph["@graph"] if n.get("@type") == "Product")
    offers = prod["offers"]
    if drop:
        offers[:] = [o for o in offers if o["seller"]["name"] != drop]
    if price_bump:
        for o in offers:
            if o["seller"]["name"] == price_bump:
                o["price"] = round(o["price"] + 1, 2)
    if extra_seller:
        o = dict(offers[0])
        o["seller"] = {"@type": "Organization", "name": extra_seller}
        o["price"] = 49.0
        offers.append(o)
    return (html[:m.start(2)] + json.dumps(graph) + html[m.end(2):]).encode()


def _events(ctx):
    with ctx.session_factory() as s:
        return [(e.kind, e.seller) for e in s.scalars(select(SellerOfferEventRow).order_by(SellerOfferEventRow.id))]


def test_new_seller_detection_end_to_end(ctx):
    base = routes_for(GAMIVO)
    rep1 = run_scan(ctx.session_factory, _gamivo(base), ctx.settings, NOW, trigger="test")
    assert rep1.status.value == "ok" and rep1.offers_seen == 5
    assert rep1.seller_events == {"baseline": 5, "new_seller_offer": 0, "returned": 0, "price_change": 0, "gone": 0}

    r2 = dict(base)
    r2[URL] = (200, {"content-type": "text/html"}, _body_with("Fresh Seller", drop="zero zero", price_bump="Digital Galaxy"))
    rep2 = run_scan(ctx.session_factory, _gamivo(r2), ctx.settings, NOW + timedelta(minutes=5), trigger="test")
    assert rep2.seller_events["new_seller_offer"] == 1 and rep2.seller_events["gone"] == 1
    assert rep2.seller_events["price_change"] == 1
    ev = _events(ctx)
    assert ("new_seller_offer", "Fresh Seller") in ev and ("gone", "zero zero") in ev

    # page down -> disturbance, offers must NOT be declared gone
    r3 = dict(base)
    r3[URL] = (403, {"content-type": "text/html"}, b"challenge")
    rep3 = run_scan(ctx.session_factory, _gamivo(r3), ctx.settings, NOW + timedelta(minutes=10), trigger="test")
    assert rep3.status.value == "failed" and sum(rep3.seller_events.values()) == 0
    with ctx.session_factory() as s:
        active = {r.seller for r in s.scalars(select(SellerOfferRow).where(SellerOfferRow.active.is_(True)))}
    assert "Fresh Seller" in active

    # back with the original page -> zero zero returns, Fresh Seller gone
    rep4 = run_scan(ctx.session_factory, _gamivo(base), ctx.settings, NOW + timedelta(minutes=15), trigger="test")
    assert rep4.seller_events["returned"] == 1 and rep4.seller_events["gone"] == 1


def test_all_marketplace_routes_blocked_never_price_find(ctx):
    rep = run_scan(ctx.session_factory, _gamivo(routes_for(GAMIVO)), ctx.settings, NOW, trigger="test")
    assert set(rep.statuses.values()) == {"blocked"} and rep.alerts_enqueued == 0


def test_backup_restore_and_retention(ctx, tmp_path):
    run_scan(ctx.session_factory, _gamivo(routes_for(GAMIVO)), ctx.settings, NOW, trigger="test")
    info = create_backup(ctx.settings, now=NOW)
    assert info["counts"]["offer_snapshots"] == 5 and info["counts"]["rule_versions"] >= 1
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


def test_health_json_fields_and_stale_source(tmp_path):
    prod = make_settings(tmp_path, config_path=__import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "production.toml")
    ctx = AppContext(prod)
    ctx.init_db(now=NOW)
    run_scan(ctx.session_factory, _gamivo(routes_for(GAMIVO)), ctx.settings, NOW, trigger="test")
    with ctx.session_factory() as s:
        body, code = compute_health(s, ctx.settings, NOW + timedelta(hours=3))
    keys = {x["key"] for x in body["sources"]}
    assert "recharge-com-de" in body["stale_sources"]  # scheduled, never succeeded
    assert "dundle-com-de" not in body["stale_sources"]  # disabled after sustained access block
    assert "gamivo-com" in keys and "gamivo-com" not in body["stale_sources"]  # not scheduled (blocked)
    assert body["heartbeat"]["stale"] is True
    names = {j["name"] for j in body["jobs"]}
    assert {"recharge_watch", "backup_daily"} <= names
    assert not {"dundle_watch", "dundle_sellers"} & names
    assert not {"gamivo_watch", "gamivo_sellers"} & names
    ctx.dispose()


@pytest.mark.parametrize("key", ["coingate", "buysellvouchers", "cardbear", "giftcardwiki"])
def test_health_tracks_scheduled_aggregators_before_first_success(tmp_path, now, key):
    from pathlib import Path

    settings = make_settings(tmp_path, config_path=Path(__file__).resolve().parents[1] / "config" / "production.toml")
    ctx = AppContext(settings)
    try:
        ctx.init_db(now=now)
        with ctx.session_factory() as s:
            body, _ = compute_health(s, settings, now)
        src = next(x for x in body["sources"] if x["key"] == key)
        assert src["scheduled"] and src["stale"]
        assert key in body["stale_sources"]
        assert src["max_age_s"] == settings.file_config.scheduler.stale_factor * 1800
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
