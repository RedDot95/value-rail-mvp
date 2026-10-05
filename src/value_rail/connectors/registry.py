"""Build connectors from config. Only the offline fixture connector is runnable in Delivery 1."""

from __future__ import annotations

from pathlib import Path

from ..settings import Settings
from .base import Connector
from .fixture import FixtureConnector
from .placeholders import PlaceholderConnector


def build_connectors(settings: Settings, *, down_sources: set[str] | None = None) -> list[Connector]:
    out: list[Connector] = []
    for c in settings.file_config.connectors:
        if not c.enabled:
            continue
        if c.kind == "fixture":
            out.append(FixtureConnector(Path(settings.fixtures_dir), down_sources=down_sources))
        elif c.kind == "placeholder":
            raise RuntimeError(f"connector {c.key!r} is a placeholder and cannot be enabled in Delivery 1")
        else:
            raise RuntimeError(f"unknown connector kind {c.kind!r}")
    return out


def describe_connectors(settings: Settings) -> list[dict]:
    rows = []
    for c in settings.file_config.connectors:
        if c.kind == "fixture":
            caps = FixtureConnector(Path(settings.fixtures_dir)).capabilities()
        else:
            caps = PlaceholderConnector(c.key, c.product_family or "unknown", c.notes).capabilities()
        rows.append({"key": c.key, "kind": c.kind, "enabled": c.enabled, "notes": c.notes,
                     "capabilities": caps.model_dump()})
    return rows
