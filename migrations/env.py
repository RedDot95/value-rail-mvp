"""Alembic environment. URL comes from the Config (programmatic) or from VALUE_RAIL_* settings."""

from __future__ import annotations

from alembic import context
from sqlalchemy import pool

from value_rail.settings import get_settings
from value_rail.storage.db import make_engine
from value_rail.storage.orm import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # Programmatic runs (value_rail.storage.db.migrate) set sqlalchemy.url; the plain
    # `alembic -c pyproject.toml ...` CLI has no ini section, so fall back to settings.
    url = None
    if config.file_config.has_section(config.config_ini_section):
        url = config.get_main_option("sqlalchemy.url")
    return url or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url(), poolclass=pool.NullPool)  # no pooled connections left behind
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
