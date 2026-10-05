"""Scheduler (Delivery 3 basics).

- Overlap protection: a DB lease (`scheduler_locks`) - only one worker process runs jobs; a crashed
  holder's lease expires after `lock_ttl_seconds`. A second worker stays in standby.
- Persistent job state (`job_states`): next_due_at, last success/error, failure streak, run counters.
- Bounded catch-up: after downtime a due job runs at most `max_catchup_runs` times back-to-back; the
  remaining missed slots are counted as skipped (no backlog storm against live sources).
- Heartbeat file (JSON, atomic replace) after every tick, for an external watcher; /healthz reads the
  same job state from the DB.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..alerts.dispatcher import dispatch_pending
from ..alerts.sinks import build_sink_from_settings
from ..connectors.base import Connector
from ..connectors.registry import build_connectors, build_one, connector_config
from ..domain.timeutil import utcnow
from ..services import AppContext
from ..settings import JobConfig
from ..storage.orm import JobStateRow, SchedulerLockRow
from .scan import ScanReport, run_scan

log = logging.getLogger("value_rail.scheduler")
LOCK_NAME = "scheduler"


def default_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def holder_is_dead_local(owner: str, *, hostname: str | None = None,
                         alive: Callable[[int], bool] = _pid_alive) -> bool:
    """True only if the lease owner ran on THIS host and its pid no longer exists (crash/kill -9).

    Unknown formats, other hosts or a live pid -> False (wait for the TTL, the safe default).
    """
    parts = owner.split(":")
    if len(parts) != 3 or parts[0] != (hostname or socket.gethostname()):
        return False
    try:
        pid = int(parts[1])
    except ValueError:
        return False
    return pid != os.getpid() and not alive(pid)


class DbLease:
    def __init__(self, session_factory: sessionmaker[Session], name: str, owner: str, ttl_seconds: int,
                 dead_check: Callable[[str], bool] = holder_is_dead_local) -> None:
        self.sf, self.name, self.owner, self.ttl = session_factory, name, owner, ttl_seconds
        self.dead_check = dead_check

    def acquire(self, now: datetime) -> bool:
        exp = now + timedelta(seconds=self.ttl)
        h = self.holder()
        if h is not None and h.owner != self.owner and h.expires_at >= now and self.dead_check(h.owner):
            with self.sf.begin() as s:  # crashed local holder: take over immediately (conditional on same owner)
                res = s.execute(update(SchedulerLockRow)
                                .where(SchedulerLockRow.name == self.name, SchedulerLockRow.owner == h.owner)
                                .values(owner=self.owner, acquired_at=now, expires_at=exp))
            if res.rowcount == 1:
                log.warning("took over scheduler lease from dead local holder %s", h.owner)
                return True
        with self.sf.begin() as s:
            res = s.execute(update(SchedulerLockRow)
                            .where(SchedulerLockRow.name == self.name,
                                   (SchedulerLockRow.expires_at < now) | (SchedulerLockRow.owner == self.owner))
                            .values(owner=self.owner, acquired_at=now, expires_at=exp))
            if res.rowcount == 1:
                return True
        try:
            with self.sf.begin() as s:
                s.add(SchedulerLockRow(name=self.name, owner=self.owner, acquired_at=now, expires_at=exp))
            return True
        except IntegrityError:
            return False

    def renew(self, now: datetime) -> bool:
        with self.sf.begin() as s:
            res = s.execute(update(SchedulerLockRow)
                            .where(SchedulerLockRow.name == self.name, SchedulerLockRow.owner == self.owner)
                            .values(expires_at=now + timedelta(seconds=self.ttl)))
            return res.rowcount == 1

    def release(self) -> None:
        with self.sf.begin() as s:
            s.execute(delete(SchedulerLockRow).where(SchedulerLockRow.name == self.name,
                                                     SchedulerLockRow.owner == self.owner))

    def holder(self) -> SchedulerLockRow | None:
        with self.sf() as s:
            return s.get(SchedulerLockRow, self.name)


def enabled_jobs(ctx: AppContext) -> list[JobConfig]:
    out = []
    for j in ctx.settings.file_config.jobs:
        if not j.enabled:
            continue
        if j.kind == "backup":
            out.append(j)
            continue
        c = connector_config(ctx.settings, j.connector)
        if c is None or not c.enabled:
            log.warning("job %s skipped: connector %r missing or disabled", j.name, j.connector)
            continue
        out.append(j)
    return out


def effective_interval(j: JobConfig) -> int:
    """Configured interval, but never below the job's floor (source limits / politeness)."""
    return max(int(j.interval_seconds), int(j.min_interval_seconds))


def sync_job_states(ctx: AppContext, now: datetime) -> None:
    with ctx.session_factory.begin() as s:
        for j in enabled_jobs(ctx):
            row = s.get(JobStateRow, j.name)
            interval = effective_interval(j)
            conn_key = j.connector if j.kind == "scan" else f"<{j.kind}>"
            if row is None:
                s.add(JobStateRow(name=j.name, connector=conn_key, interval_seconds=interval,
                                  next_due_at=now, last_status="never_run", last_error="", consecutive_failures=0,
                                  runs_total=0, skipped_catchup_total=0))
            elif row.interval_seconds != interval or row.connector != conn_key:
                row.interval_seconds, row.connector = interval, conn_key


def _missed_slots(due: datetime, now: datetime, interval: int) -> int:
    """Number of whole intervals that elapsed after the due time (0 = on time)."""
    if now <= due:
        return 0
    return int((now - due).total_seconds() // interval)


class Scheduler:
    def __init__(self, ctx: AppContext, *, owner: str | None = None, clock: Callable[[], datetime] = utcnow,
                 connector_factory: Callable[[str], Connector] | None = None, dispatch: bool = True) -> None:
        self.ctx = ctx
        self.cfg = ctx.settings.file_config.scheduler
        self.owner = owner or default_owner()
        self.clock = clock
        self.lease = DbLease(ctx.session_factory, LOCK_NAME, self.owner, self.cfg.lock_ttl_seconds)
        self.connector_factory = connector_factory or self._build_connector
        self.dispatch = dispatch
        self._connectors: dict[str, Connector] = {}
        self.heartbeat_path = Path(ctx.settings.effective_heartbeat_file)

    def _build_connector(self, key: str) -> Connector:
        if key not in self._connectors:  # keep one instance -> politeness state (robots, intervals) persists
            self._connectors[key] = build_one(self.ctx.settings, connector_config(self.ctx.settings, key))
        return self._connectors[key]

    def tick(self) -> dict[str, Any]:
        now = self.clock()
        result: dict[str, Any] = {"at": now.isoformat(), "owner": self.owner, "lock_held": False, "ran": [],
                                  "skipped_catchup": {}}
        if not self.lease.acquire(now):
            h = self.lease.holder()
            result["standby_for"] = h.owner if h else "unknown"
            log.info("another scheduler holds the lease (%s); standby", result["standby_for"])
            self.write_heartbeat(now, result)
            return result
        result["lock_held"] = True
        sync_job_states(self.ctx, now)
        with self.ctx.session_factory() as s:
            due = [r for r in s.scalars(select(JobStateRow).order_by(JobStateRow.name)).all()
                   if r.name in {j.name for j in enabled_jobs(self.ctx)} and r.next_due_at is not None
                   and r.next_due_at <= now]
        jobs = {j.name: j for j in enabled_jobs(self.ctx)}
        for st in due:
            missed = _missed_slots(st.next_due_at, now, st.interval_seconds)
            runs = min(missed + 1, max(1, self.cfg.max_catchup_runs))
            for _ in range(runs):
                self._run_job(st.name, st.connector, trigger=f"scheduler:{st.name}", job=jobs.get(st.name))
                result["ran"].append(st.name)
                self.lease.renew(self.clock())
            skipped = missed + 1 - runs
            done = self.clock()
            with self.ctx.session_factory.begin() as s:
                row = s.get(JobStateRow, st.name)
                row.next_due_at = done + timedelta(seconds=row.interval_seconds)
                row.skipped_catchup_total += skipped
            if skipped:
                result["skipped_catchup"][st.name] = skipped
                log.warning("job %s: %s missed slot(s) skipped (bounded catch-up)", st.name, skipped)
        if self.dispatch and result["ran"]:
            try:
                sink = build_sink_from_settings(self.ctx.settings)
                dispatch_pending(self.ctx.session_factory, sink, self.clock(),
                                 backoff_seconds=self.ctx.settings.file_config.alerts.retry_backoff_seconds)
            except Exception:  # noqa: BLE001 - alert problems must not stop scanning; outbox keeps them
                log.exception("alert dispatch failed (alerts stay in outbox)")
        self.write_heartbeat(self.clock(), result)
        return result

    def _run_job(self, name: str, connector_key: str, *, trigger: str,
                 job: JobConfig | None = None) -> ScanReport | None:
        started = self.clock()
        with self.ctx.session_factory.begin() as s:
            row = s.get(JobStateRow, name)
            row.last_started_at = started
            row.runs_total += 1
        rep: ScanReport | None = None
        err = ""
        try:
            if job is not None and job.kind == "backup":
                from ..backup import run_backup_job  # local import: backup is optional for scans
                info = run_backup_job(self.ctx.settings, now=started)
                status = "ok" if info.get("ok") else "failed"
                if not info.get("ok"):
                    err = json.dumps(info, sort_keys=True, default=str)[:2000]
            else:
                conn = self.connector_factory(connector_key)
                configure = getattr(conn, "configure_for_job", None)
                if configure is not None:
                    configure(dict(job.options) if job is not None else {})
                rep = run_scan(self.ctx.session_factory, conn, self.ctx.settings, started, trigger=trigger)
                status = rep.status.value
            if rep is not None and rep.sources_failed:
                err = json.dumps(rep.sources_failed, sort_keys=True)[:2000]
        except Exception as exc:  # noqa: BLE001 - recorded in job state, loop stays alive
            log.exception("job %s crashed", name)
            status, err = "failed", f"{type(exc).__name__}: {exc}"[:2000]
        finished = self.clock()
        with self.ctx.session_factory.begin() as s:
            row = s.get(JobStateRow, name)
            row.last_finished_at = finished
            row.last_status = status
            row.last_scan_run_id = rep.scan_run_id if rep else row.last_scan_run_id
            if status == "ok":
                row.last_success_at = finished
                row.consecutive_failures = 0
                row.last_error = ""
            else:
                row.last_error_at = finished
                row.last_error = err
                row.consecutive_failures += 1
        return rep

    def write_heartbeat(self, now: datetime, tick: dict[str, Any]) -> None:
        with self.ctx.session_factory() as s:
            jobs = {r.name: {"last_status": r.last_status,
                             "last_success_at": r.last_success_at.isoformat() if r.last_success_at else None,
                             "next_due_at": r.next_due_at.isoformat() if r.next_due_at else None,
                             "consecutive_failures": r.consecutive_failures,
                             "interval_seconds": r.interval_seconds}
                    for r in s.scalars(select(JobStateRow)).all()}
        data = {"written_at": now.isoformat(), "pid": os.getpid(), "owner": self.owner,
                "lock_held": tick.get("lock_held", False), "ran": tick.get("ran", []), "jobs": jobs}
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.heartbeat_path.with_suffix(self.heartbeat_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.heartbeat_path)

    def run_forever(self, *, max_ticks: int | None = None, sleep: Callable[[float], None] = time.sleep,
                    should_stop: Callable[[], bool] = lambda: False) -> None:
        n = 0
        try:
            while not should_stop() and (max_ticks is None or n < max_ticks):
                try:
                    self.tick()
                except Exception:  # noqa: BLE001
                    log.exception("scheduler tick failed")
                n += 1
                if max_ticks is not None and n >= max_ticks:
                    break
                sleep(self.cfg.tick_seconds)
        finally:
            self.lease.release()


# ---- backwards-compatible helpers used by the CLI (`load-fixtures`/`scan`) ----

def run_cycle(ctx: AppContext, *, now: datetime | None = None, down_sources: set[str] | None = None,
              dispatch: bool = True, trigger: str = "worker") -> list[ScanReport]:
    """One immediate scan over all ENABLED connectors (no lease/job state; used by `value-rail scan`)."""
    now = now or utcnow()
    reports = [run_scan(ctx.session_factory, c, ctx.settings, now, trigger=trigger)
               for c in build_connectors(ctx.settings, down_sources=down_sources)]
    if dispatch:
        sink = build_sink_from_settings(ctx.settings)
        dispatch_pending(ctx.session_factory, sink, now,
                         backoff_seconds=ctx.settings.file_config.alerts.retry_backoff_seconds)
    return reports


def run_forever(ctx: AppContext, *, max_cycles: int | None = None) -> None:
    import signal

    stop = {"flag": False}

    def _term(signum, frame):  # graceful stop: finish the current job, release the lease
        stop["flag"] = True

    try:
        signal.signal(signal.SIGTERM, _term)
    except ValueError:  # not in main thread
        pass
    Scheduler(ctx).run_forever(max_ticks=max_cycles, should_stop=lambda: stop["flag"])
