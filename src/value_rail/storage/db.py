"""Engine/session factory and programmatic Alembic migration."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..settings import Settings


def make_engine(url: str, **kwargs) -> Engine:
    if url.startswith("sqlite:///"):
        db_file = url.removeprefix("sqlite:///")
        if db_file and db_file != ":memory:":
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=FULL")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def alembic_config(settings: Settings) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(settings.migrations_dir).resolve()))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def migrate(settings: Settings) -> None:
    """Apply all migrations (alembic upgrade head)."""
    command.upgrade(alembic_config(settings), "head")
