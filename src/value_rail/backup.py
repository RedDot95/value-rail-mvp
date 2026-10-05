"""Online SQLite backup + restore test.

- `create_backup` uses sqlite3's online backup API (`Connection.backup`), which produces a consistent
  snapshot while the worker keeps writing (WAL or rollback journal - both fine).
- Retention: keep the newest `keep` backups (default 14 = two weeks of daily backups).
- `restore_test` restores a backup into a fresh temp file (again via the backup API, i.e. exactly the
  restore procedure documented in docs/operations.md), runs `PRAGMA integrity_check` and compares row
  counts of the key tables between the backup file and the restored copy.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .settings import Settings

COUNT_TABLES = ("offer_snapshots", "rule_versions", "alerts", "route_evaluations", "evidence", "scan_runs",
                "seller_offers", "seller_offer_events")
PREFIX = "value_rail_"


def db_file(settings: Settings) -> Path:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise ValueError(f"backup supports sqlite file databases only, got {url.split(':', 1)[0]}")
    return Path(url[len("sqlite:///"):])


def table_counts(path: Path) -> dict[str, int | None]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: (con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] if t in names else None)
                for t in COUNT_TABLES}
    finally:
        con.close()


def _copy(src: Path, dst: Path) -> None:
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)  # online backup API: page-by-page consistent snapshot
        d.execute("PRAGMA journal_mode=DELETE")  # self-contained single file (no -wal/-shm sidecars)
    finally:
        d.close()
        s.close()


def create_backup(settings: Settings, *, now: datetime | None = None, keep: int | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    src = db_file(settings)
    if not src.exists():
        raise FileNotFoundError(f"database {src} does not exist")
    out_dir = Path(settings.backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{PREFIX}{now.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}.db"
    tmp = dst.with_suffix(".db.part")
    _copy(src, tmp)
    tmp.replace(dst)
    dst.chmod(0o600)
    removed = prune(out_dir, keep if keep is not None else settings.backup_keep)
    return {"backup": str(dst), "bytes": dst.stat().st_size, "counts": table_counts(dst), "removed": removed,
            "created_at_utc": now.isoformat()}


def list_backups(out_dir: Path) -> list[Path]:
    return sorted(Path(out_dir).glob(f"{PREFIX}*.db"))


def prune(out_dir: Path, keep: int) -> list[str]:
    keep = max(1, int(keep))
    files = list_backups(out_dir)
    old = files[:-keep] if len(files) > keep else []
    for f in old:
        for side in (f, Path(str(f) + "-wal"), Path(str(f) + "-shm")):
            side.unlink(missing_ok=True)
    return [str(f) for f in old]


def restore_test(backup: Path) -> dict[str, Any]:
    backup = Path(backup)
    try:
        return _restore_test(backup)
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "backup": str(backup), "integrity_check": f"error: {exc}", "expected_counts": None,
                "restored_counts": None}


def _restore_test(backup: Path) -> dict[str, Any]:
    expected = table_counts(backup)
    with tempfile.TemporaryDirectory(prefix="vr-restore-") as td:
        target = Path(td) / "restored.db"
        _copy(backup, target)  # restore = backup API in the other direction
        con = sqlite3.connect(target)
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
        got = table_counts(target)
    ok = integrity == "ok" and got == expected
    return {"ok": ok, "backup": str(backup), "integrity_check": integrity, "expected_counts": expected,
            "restored_counts": got}


def run_backup_job(settings: Settings, *, now: datetime | None = None) -> dict[str, Any]:
    info = create_backup(settings, now=now)
    rt = restore_test(Path(info["backup"]))
    info["restore_test"] = rt
    info["ok"] = bool(rt["ok"])
    status_file = Path(settings.backup_dir) / "last_backup.json"
    status_file.write_text(json.dumps(info, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return info


def last_backup_status(settings: Settings) -> dict[str, Any] | None:
    f = Path(settings.backup_dir) / "last_backup.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
