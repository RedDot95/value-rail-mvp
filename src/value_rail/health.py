"""Health model shared by `/healthz` and `value-rail health` (for an external watcher).

status:
- ok        all enabled jobs succeeded within stale_factor x interval
- starting  some enabled job has not succeeded yet but is still inside its grace window
- degraded  a job's last run was degraded/failed but its last success is still fresh
- stale     a job has no success within stale_factor x interval (-> HTTP 503)
- failing   a job has run but never succeeded (-> HTTP 503)
- no_jobs   no scheduler job enabled (UI-only deployment)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain.timeutil import to_display
from .settings import Settings
from .storage.orm import JobStateRow, SourceRow


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def compute_health(s: Session, settings: Settings, now: datetime) -> tuple[dict[str, Any], int]:
    cfg = settings.file_config
    factor = cfg.scheduler.stale_factor
    enabled = {j.name: j for j in cfg.jobs if j.enabled and any(c.key == j.connector and c.enabled
                                                                  for c in cfg.connectors)}
    rows = {r.name: r for r in s.scalars(select(JobStateRow)).all()}
    jobs, states = [], []
    for name, j in enabled.items():
        r = rows.get(name)
        limit = factor * j.interval_seconds
        last_ok = r.last_success_at if r else None
        age = (now - last_ok).total_seconds() if last_ok else None
        if last_ok is not None and age <= limit:
            st = "ok" if r.last_status == "ok" else "degraded"
        elif last_ok is None and r is not None and r.runs_total > 0:
            st = "failing"  # ran, but never succeeded
        elif last_ok is None and r is not None and r.next_due_at and (now - r.next_due_at).total_seconds() <= limit:
            st = "starting"
        elif r is None:
            st = "starting"  # scheduler has not registered the job yet
        else:
            st = "stale"
        states.append(st)
        jobs.append({"name": name, "connector": j.connector, "interval_seconds": j.interval_seconds, "state": st,
                     "last_status": r.last_status if r else "never_run", "last_success_at": _iso(last_ok),
                     "last_success_berlin": to_display(last_ok) if last_ok else None,
                     "last_success_age_s": round(age, 1) if age is not None else None,
                     "consecutive_failures": r.consecutive_failures if r else 0,
                     "last_error": (r.last_error[:300] if r and r.last_error else ""),
                     "next_due_at": _iso(r.next_due_at) if r else None})
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
    hb: dict[str, Any] = {"path": str(hb_path), "present": hb_path.exists()}
    if hb_path.exists():
        try:
            data = json.loads(hb_path.read_text(encoding="utf-8"))
            written = datetime.fromisoformat(data["written_at"])
            hb.update(written_at=data["written_at"], age_s=round((now - written).total_seconds(), 1),
                      owner=data.get("owner"), lock_held=data.get("lock_held"))
        except (ValueError, KeyError, OSError) as exc:
            hb["error"] = f"unreadable heartbeat: {type(exc).__name__}"
    sources = [{"key": x.key, "health": x.health, "last_success_at": _iso(x.last_success_at), "last_error": (x.last_error or "")[:300],
                "synthetic": x.is_synthetic}
               for x in s.scalars(select(SourceRow).order_by(SourceRow.key)).all()]
    live = any(c.enabled and c.kind not in ("fixture", "placeholder") for c in cfg.connectors)
    body = {"status": overall, "checked_at": now.isoformat(), "live_scanning": live, "jobs": jobs,
            "heartbeat": hb, "sources": sources,
            "telegram_configured": settings.telegram_configured and "telegram" in cfg.alerts.sink}
    return body, (503 if overall in ("stale", "failing") else 200)
