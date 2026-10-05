"""Outbox dispatcher with limited retries. Safe to run after a restart."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..domain.enums import AlertState
from ..storage.orm import AlertRow
from .sinks import AlertSink

log = logging.getLogger("value_rail.dispatcher")


class DispatchReport(BaseModel):
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    dead: int = 0


def dispatch_pending(session_factory: sessionmaker[Session], sink: AlertSink, now: datetime,
                     backoff_seconds: int = 60, limit: int = 100) -> DispatchReport:
    rep = DispatchReport()
    with session_factory() as s:
        ids = list(s.scalars(select(AlertRow.id).where(AlertRow.state == AlertState.PENDING.value,
                                                        AlertRow.next_attempt_at <= now)
                             .order_by(AlertRow.id).limit(limit)))
    for alert_id in ids:
        # one short transaction per alert: a crash affects at most the alert in flight
        with session_factory.begin() as s:
            a = s.get(AlertRow, alert_id)
            if a is None or a.state != AlertState.PENDING.value:
                continue
            rep.attempted += 1
            a.attempts += 1
            try:
                sink.send(a.payload | {"attempt": a.attempts})
            except Exception as exc:  # noqa: BLE001 - any sink failure is retried
                a.last_error = f"{type(exc).__name__}: {exc}"
                if a.attempts >= a.max_attempts:
                    a.state = AlertState.DEAD.value
                    rep.dead += 1
                    log.error("alert %s dead after %s attempts: %s", a.event_id, a.attempts, a.last_error)
                else:
                    a.next_attempt_at = now + timedelta(seconds=backoff_seconds * a.attempts)
                    rep.failed += 1
                    log.warning("alert %s attempt %s failed: %s", a.event_id, a.attempts, a.last_error)
                continue
            a.state = AlertState.SENT.value
            a.sent_at = now
            a.last_error = None
            rep.sent += 1
    return rep
