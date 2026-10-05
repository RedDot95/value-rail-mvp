"""Scheduler STUB (Delivery 1).

Bauauftrag intervals are read from config (watchlist 5 min, new sellers 30 min, aggregators daily).
Delivery 1 only has the offline fixture connector, so the loop runs the fixture scan on the
watchlist interval and dispatches the outbox. It is NOT a 24/7 production scheduler: no
heartbeat monitoring, no lease/lock, no per-source-class queues yet (see docs/operations.md).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from ..alerts.dispatcher import dispatch_pending
from ..alerts.sinks import build_sink
from ..connectors.registry import build_connectors
from ..domain.timeutil import utcnow
from ..services import AppContext
from .scan import ScanReport, run_scan

log = logging.getLogger("value_rail.scheduler")


def run_cycle(ctx: AppContext, *, now: datetime | None = None, down_sources: set[str] | None = None,
              dispatch: bool = True, trigger: str = "worker") -> list[ScanReport]:
    now = now or utcnow()
    cfg = ctx.settings.file_config
    reports = []
    for connector in build_connectors(ctx.settings, down_sources=down_sources):
        reports.append(run_scan(ctx.session_factory, connector, ctx.settings, now, trigger=trigger))
    if dispatch:
        sink = build_sink(cfg.alerts.sink, ctx.settings.effective_alert_log_file)
        dispatch_pending(ctx.session_factory, sink, now, backoff_seconds=cfg.alerts.retry_backoff_seconds)
    return reports


def run_forever(ctx: AppContext, *, max_cycles: int | None = None) -> None:
    interval = ctx.settings.file_config.scan_intervals.watchlist_seconds
    n = 0
    while max_cycles is None or n < max_cycles:
        started = time.monotonic()
        try:
            for r in run_cycle(ctx):
                log.info("scan %s: %s, %s evaluations, %s alerts, failed=%s", r.scan_run_id, r.status,
                         r.evaluations_created, r.alerts_enqueued, r.sources_failed)
        except Exception:  # noqa: BLE001 - keep loop alive, error is logged
            log.exception("scan cycle failed")
        n += 1
        if max_cycles is not None and n >= max_cycles:
            break
        time.sleep(max(0.0, interval - (time.monotonic() - started)))
