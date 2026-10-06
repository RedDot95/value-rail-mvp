"""Build connectors from config. Live connectors are only built when explicitly enabled (or for smoke tests)."""

from __future__ import annotations

from pathlib import Path

from ..settings import ConnectorConfig, Settings
from .aggregators import AGGREGATOR_KINDS, build_aggregator
from .base import Connector
from .fixture import FixtureConnector
from .placeholders import PlaceholderConnector
from .jsonld_shop import JsonLdShopConfig, JsonLdShopConnector
from .recharge import RechargeConfig, RechargeConnector


def connector_config(settings: Settings, key: str) -> ConnectorConfig | None:
    return next((c for c in settings.file_config.connectors if c.key == key), None)


def build_one(settings: Settings, c: ConnectorConfig, *, down_sources: set[str] | None = None, **kw) -> Connector:
    if c.kind == "fixture":
        return FixtureConnector(Path(settings.fixtures_dir), down_sources=down_sources)
    if c.kind == "recharge":
        return RechargeConnector(RechargeConfig.model_validate(c.options), **kw)
    if c.kind == "jsonld_shop":
        return JsonLdShopConnector(JsonLdShopConfig.model_validate(c.options), **kw)
    if c.kind in AGGREGATOR_KINDS:  # always discovery_only (hard-wired in the connector class)
        return build_aggregator(c.kind, c.options, **kw)
    if c.kind in ("placeholder", "blocked"):
        raise RuntimeError(f"connector {c.key!r} is a placeholder (not implemented) and cannot be enabled")
    raise RuntimeError(f"unknown connector kind {c.kind!r}")


def build_connectors(settings: Settings, *, down_sources: set[str] | None = None,
                     only: set[str] | None = None) -> list[Connector]:
    out: list[Connector] = []
    for c in settings.file_config.connectors:
        if not c.enabled or (only is not None and c.key not in only):
            continue
        out.append(build_one(settings, c, down_sources=down_sources))
    return out


def describe_connectors(settings: Settings) -> list[dict]:
    rows = []
    for c in settings.file_config.connectors:
        if c.kind == "fixture":
            caps = FixtureConnector(Path(settings.fixtures_dir)).capabilities()
        elif c.kind == "recharge":
            caps = RechargeConnector(RechargeConfig.model_validate(c.options)).capabilities()
        elif c.kind == "jsonld_shop":
            caps = JsonLdShopConnector(JsonLdShopConfig.model_validate(c.options)).capabilities()
        elif c.kind in AGGREGATOR_KINDS:
            caps = build_aggregator(c.kind, c.options).capabilities()
        else:
            caps = PlaceholderConnector(c.key, c.product_family or "unknown", c.notes).capabilities()
        rows.append({"key": c.key, "kind": c.kind, "enabled": c.enabled, "notes": c.notes,
                     "capabilities": caps.model_dump()})
    return rows
