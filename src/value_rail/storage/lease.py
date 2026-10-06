"""Renewable DB leases shared by scheduler and alert dispatcher."""
from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .orm import SchedulerLockRow

log = logging.getLogger("value_rail.lease")


class LeaseLostError(RuntimeError):
    pass


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
    return pid > 0 and pid != os.getpid() and not alive(pid)


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
                            .where(SchedulerLockRow.name == self.name, SchedulerLockRow.owner == self.owner,
                                   SchedulerLockRow.expires_at > now)
                            .values(expires_at=now + timedelta(seconds=self.ttl)))
            return res.rowcount == 1

    def release(self) -> None:
        with self.sf.begin() as s:
            s.execute(delete(SchedulerLockRow).where(SchedulerLockRow.name == self.name,
                                                     SchedulerLockRow.owner == self.owner))

    def holder(self) -> SchedulerLockRow | None:
        with self.sf() as s:
            return s.get(SchedulerLockRow, self.name)



class LeaseKeeper:
    """Renew during network I/O; fence DB writes by renewing in their transaction.

    A failed renewal is fail-closed. Already running network requests cannot be
    cancelled here, but their results cannot be committed after ownership loss.
    """

    def __init__(self, lease: DbLease, clock: Callable[[], datetime]) -> None:
        self.lease, self.clock = lease, clock
        self.stopped = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(target=self._run, name="lease-keeper", daemon=True)

    def __enter__(self):
        self.check()
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stopped.set()
        self.thread.join()

    def _run(self) -> None:
        while not self.stopped.wait(max(0.05, self.lease.ttl / 3)):
            try:
                self.check()
            except Exception:
                self.lost.set()
                log.warning("lease renewal failed for %s; stop committing work", self.lease.name)
                return

    def check(self, s: Session | None = None) -> None:
        if self.lost.is_set():
            raise LeaseLostError(f"lease lost: {self.lease.name}")
        now = self.clock()
        if s is None:
            ok = self.lease.renew(now)
        else:
            res = s.execute(update(SchedulerLockRow).where(
                SchedulerLockRow.name == self.lease.name,
                SchedulerLockRow.owner == self.lease.owner,
                SchedulerLockRow.expires_at > now).values(expires_at=now + timedelta(seconds=self.lease.ttl)))
            ok = res.rowcount == 1
        if not ok:
            self.lost.set()
            raise LeaseLostError(f"lease lost: {self.lease.name}")
