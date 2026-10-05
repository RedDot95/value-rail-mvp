"""Health model shared by `/healthz` and `value-rail health` (for an external watcher).

status:
- ok        all enabled jobs succeeded within stale_factor x interval
- starting  some enabled job has not succeeded yet but is still inside its grace window
- degraded  a job's last run was degraded/failed but its last success is still fresh
- stale     a job has no success within stale_factor x interval (-> HTTP 503)
- failing   a job has run but never succeeded (-> HTTP 503)
- no_jobs   no scheduler job enabled (UI-only deployment)
A worker heartbeat older than `heartbeat_stale_s` also makes the status `stale` (worker dead/hung).

Extra fields for an external watcher (all cheap COUNT/primary-key queries):
- heartbeat.age_s / heartbeat.stale
- sources[].last_success_age_s / stale / max_age_s (per-source freshness derived from its jobs)
- stale_sources: keys of scheduled sources without a fresh success
- alerts: open alert outbox rows by state (pending / dead)
- jobs[].last_scan: counts of the job's last scan run (candidates, evaluations, offers, statuses, seller events)
- backup: last backup + restore-test result
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .domain.timeutil import to_display
from .settings import Settings
from .storage.orm import (AlertRow, JobStateRow, OfferSnapshotRow, RouteEvaluationRow, ScanRunRow,
                          SellerOfferEventRow, SourceRow)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def connector_source_keys(c) -> list[str]:
    """Source keys a connector writes (without instantiating it)."""
    if c.kind == "jsonld_shop":
        return [str(c.options.get("source_key", c.key))]
    if c.kind == "recharge":
        return ["recharge-com-de"]
    return []


def _scan_counts(s: Session, scan_id: int | None) -> dict[str, Any] | None:
    if scan_id is None:
        return None
    scan = s.get(ScanRunRow, scan_id)
    if scan is None:
        return None
    statuses = dict(s.execute(select(RouteEvaluationRow.status, func.count()).where(
        RouteEvaluationRow.scan_run_id == scan_id).group_by(RouteEvaluationRow.status)).all())
    offers = s.scalar(select(func.count()).select_from(OfferSnapshotRow).where(OfferSnapshotRow.scan_run_id == scan_id))
    events = dict(s.execute(select(SellerOfferEventRow.kind, func.count()).where(
        SellerOfferEventRow.scan_run_id == scan_id).group_by(SellerOfferEventRow.kind)).all())
    return {"scan_run_id": scan_id, "status": scan.status, "started_at": _iso(scan.started_at),
            "candidates": scan.items_seen, "evaluations": scan.evaluations_created, "offers": offers,
            "alerts_enqueued": scan.alerts_enqueued, "statuses": statuses, "seller_events": events,
            "sources_failed": sorted((scan.sources_failed or {}).keys())}


def _job_enabled(cfg, j) -> bool:
    if not j.enabled:
        return False
    if j.kind == "backup":
        return True
    return any(c.key == j.connector and c.enabled for c in cfg.connectors)


def compute_health(s: Session, settings: Settings, now: datetime) -> tuple[dict[str, Any], int]:
    cfg = settings.file_config
    factor = cfg.scheduler.stale_factor
    enabled = {j.name: j for j in cfg.jobs if _job_enabled(cfg, j)}
    rows = {r.name: r for r in s.scalars(select(JobStateRow)).all()}
    jobs, states = [], []
    for name, j in enabled.items():
        r = rows.get(name)
        interval = max(j.interval_seconds, j.min_interval_seconds)
        limit = factor * interval
        last_ok = r.last_success_at if r else None
        age = (now - last_ok).total_seconds() if last_ok else None
        if last_ok is not None and age <= limit:
            st = "ok" if r.last_status == "ok" else "degraded"
        elif last_ok is None and r is not None and r.runs_total == 1 and r.last_started_at is not None and \
                (r.last_finished_at is None or r.last_finished_at < r.last_started_at):
            st = "starting"  # first run still in progress
        elif last_ok is None and r is not None and r.runs_total > 0:
            st = "failing"  # ran, but never succeeded
        elif last_ok is None and r is not None and r.next_due_at and (now - r.next_due_at).total_seconds() <= limit:
            st = "starting"
        elif r is None:
            st = "starting"  # scheduler has not registered the job yet
        else:
            st = "stale"
        states.append(st)
        jobs.append({"name": name, "kind": j.kind, "connector": j.connector, "interval_seconds": interval, "state": st,
                     "last_status": r.last_status if r else "never_run", "last_success_at": _iso(last_ok),
                     "last_success_berlin": to_display(last_ok) if last_ok else None,
                     "last_success_age_s": round(age, 1) if age is not None else None,
                     "consecutive_failures": r.consecutive_failures if r else 0,
                     "last_error": (r.last_error[:300] if r and r.last_error else ""),
                     "next_due_at": _iso(r.next_due_at) if r else None,
                     "last_scan": _scan_counts(s, r.last_scan_run_id) if r and j.kind == "scan" else None})
    if not enabled:
        overall = "no_jobs"
    elif "stale" in states or "failing" in states:
        overall = "stale" if "stale" in states else "failing"
    elif "degraded" in states:
        overall = "degraded"
    elif "starting" in states:
        overall = "starting"
    else:
        overall = "ok"
    hb_path = Path(settings.effective_heartbeat_file)
    hb_limit = max(300, 4 * cfg.scheduler.tick_seconds)
    hb: dict[str, Any] = {"path": str(hb_path), "present": hb_path.exists(), "stale_after_s": hb_limit}
    if hb_path.exists():
        try:
            data = json.loads(hb_path.read_text(encoding="utf-8"))
            written = datetime.fromisoformat(data["written_at"])
            age_hb = (now - written).total_seconds()
            hb.update(written_at=data["written_at"], age_s=round(age_hb, 1), owner=data.get("owner"),
                      pid=data.get("pid"), lock_held=data.get("lock_held"), stale=age_hb > hb_limit)
        except (ValueError, KeyError, OSError) as exc:
            hb["error"] = f"unreadable heartbeat: {type(exc).__name__}"
            hb["stale"] = True
    else:
        hb["stale"] = bool(enabled)
    # a missing heartbeat during the initial grace window ("starting") is not an alarm yet
    if enabled and hb.get("stale") and overall != "failing" and (hb["present"] or overall != "starting"):
        overall = "stale"
    # per-source freshness: max age = stale_factor x shortest interval of the enabled jobs feeding it
    src_limit: dict[str, int] = {}
    conns = {c.key: c for c in cfg.connectors}
    for j in enabled.values():
        c = conns.get(j.connector)
        if j.kind != "scan" or c is None:
            continue
        for k in connector_source_keys(c):
            lim = factor * max(j.interval_seconds, j.min_interval_seconds)
            src_limit[k] = min(src_limit.get(k, lim), lim)
    sources, stale_sources = [], []
    for x in s.scalars(select(SourceRow).order_by(SourceRow.key)).all():
        age = (now - x.last_success_at).total_seconds() if x.last_success_at else None
        lim = src_limit.get(x.key)
        stale = lim is not None and (age is None or age > lim)
        if stale:
            stale_sources.append(x.key)
        sources.append({"key": x.key, "health": x.health, "last_success_at": _iso(x.last_success_at),
                        "last_success_berlin": to_display(x.last_success_at) if x.last_success_at else None,
                        "last_success_age_s": round(age, 1) if age is not None else None,
                        "scheduled": lim is not None, "max_age_s": lim, "stale": stale,
                        "last_error": (x.last_error or "")[:300], "synthetic": x.is_synthetic})
    for k in src_limit:  # scheduled but never written (e.g. first scan failed before any success)
        if not any(x["key"] == k for x in sources):
            stale_sources.append(k)
            sources.append({"key": k, "health": "unknown", "last_success_at": None, "scheduled": True,
                            "max_age_s": src_limit[k], "stale": True, "last_error": "", "synthetic": False})
    alerts = dict(s.execute(select(AlertRow.state, func.count()).where(AlertRow.state.in_(("pending", "dead")))
                            .group_by(AlertRow.state)).all())
    live = any(c.enabled and c.kind not in ("fixture", "placeholder", "blocked") for c in cfg.connectors)
    from .backup import last_backup_status
    b = last_backup_status(settings)
    backup = None if b is None else {"file": b.get("backup"), "created_at_utc": b.get("created_at_utc"),
                                     "ok": b.get("ok"), "restore_ok": (b.get("restore_test") or {}).get("ok")}
    body = {"status": overall, "checked_at": now.isoformat(), "live_scanning": live, "jobs": jobs,
            "heartbeat": hb, "sources": sources, "stale_sources": sorted(set(stale_sources)),
            "alerts_open": {"pending": alerts.get("pending", 0), "dead": alerts.get("dead", 0)},
            "backup": backup,
            "telegram_configured": settings.telegram_configured and "telegram" in cfg.alerts.sink}
    return body, (503 if overall in ("stale", "failing") else 200)
