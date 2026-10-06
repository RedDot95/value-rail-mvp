"""Leased outbox dispatcher with durable per-channel receipts and bounded retries.

Network sends happen without a DB transaction. At-least-once delivery: a crash
between external delivery and recording its receipt can still duplicate that send.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Callable

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..domain.enums import AlertState
from ..storage.lease import DbLease, LeaseKeeper, default_owner
from ..storage.orm import AlertRow
from .sinks import AlertSink, CompositeSink

log = logging.getLogger("value_rail.dispatcher")


class DispatchReport(BaseModel):
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    dead: int = 0
    suppressed: int = 0


def dispatch_pending(session_factory: sessionmaker[Session], sink: AlertSink, now: datetime,
                     backoff_seconds: int = 60, limit: int = 100, *,
                     clock: Callable[[], datetime] | None = None, guard=None, eligibility=None) -> DispatchReport:
    rep = DispatchReport()
    started = time.monotonic()
    clock = clock or (lambda: now + timedelta(seconds=time.monotonic() - started))
    lease = DbLease(session_factory, "alert_dispatch", default_owner(), ttl_seconds=300)
    if not lease.acquire(clock()):
        return rep
    try:
        with LeaseKeeper(lease, clock) as keeper:
            def check(s=None):
                if guard is not None:
                    guard(s)
                keeper.check(s)

            check()
            with session_factory() as s:
                ids = list(s.scalars(select(AlertRow.id).where(
                    AlertRow.state == AlertState.PENDING.value, AlertRow.next_attempt_at <= now)
                    .order_by(AlertRow.id).limit(limit)))
            channels = sink.sinks if isinstance(sink, CompositeSink) else [sink]
            for alert_id in ids:
                with session_factory.begin() as s:
                    check(s)
                    a = s.get(AlertRow, alert_id)
                    if a is None or a.state != AlertState.PENDING.value or a.next_attempt_at > now:
                        continue
                    if eligibility is not None:
                        eligible, reason = eligibility(s, a, clock())
                        if not eligible:
                            a.state = AlertState.SUPPRESSED.value
                            a.last_error = reason
                            rep.suppressed += 1
                            continue
                    rep.attempted += 1
                    a.attempts += 1
                    payload = a.payload | {"attempt": a.attempts}
                    done = set(a.delivered_sinks)
                errors = []
                for channel in channels:
                    if channel.name in done:
                        continue
                    check()
                    try:
                        channel.send(payload)
                    except Exception as exc:  # noqa: BLE001 - failed channels are retried
                        errors.append(f"{channel.name}: {type(exc).__name__}: {exc}")
                        continue
                    with session_factory.begin() as s:
                        check(s)
                        a = s.get(AlertRow, alert_id)
                        a.delivered_sinks = sorted(set(a.delivered_sinks) | {channel.name})
                    done.add(channel.name)
                with session_factory.begin() as s:
                    check(s)
                    a = s.get(AlertRow, alert_id)
                    if errors:
                        a.last_error = "; ".join(errors)
                        if a.attempts >= a.max_attempts:
                            a.state = AlertState.DEAD.value
                            rep.dead += 1
                            log.error("alert %s dead after %s attempts: %s", a.event_id, a.attempts, a.last_error)
                        else:
                            a.next_attempt_at = now + timedelta(seconds=backoff_seconds * a.attempts)
                            rep.failed += 1
                            log.warning("alert %s attempt %s failed: %s", a.event_id, a.attempts, a.last_error)
                    else:
                        a.state = AlertState.SENT.value
                        a.sent_at = now
                        a.last_error = None
                        rep.sent += 1
    finally:
        lease.release()
    return rep
