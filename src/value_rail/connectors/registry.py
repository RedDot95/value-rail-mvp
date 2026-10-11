"""The only live source is CoinGate Clearance; fixtures are offline test data."""
from pathlib import Path
from ..settings import ConnectorConfig, Settings
from .base import Connector
from .fixture import FixtureConnector
from .coingate_clearance import CoinGateClearanceConnector


def connector_config(settings: Settings, key: str) -> ConnectorConfig | None:
    return next((c for c in settings.file_config.connectors if c.key == key), None)


def build_one(settings: Settings, c: ConnectorConfig, *, down_sources=None, **kw) -> Connector:
    if c.kind == "fixture":
        return FixtureConnector(Path(settings.fixtures_dir), down_sources=down_sources)
    if c.kind == "coingate_clearance":
        return CoinGateClearanceConnector(**kw)
    raise RuntimeError(f"unsupported connector kind {c.kind!r}; only coingate_clearance and offline fixture exist")


def build_connectors(settings: Settings, *, down_sources=None, only=None) -> list[Connector]:
    return [build_one(settings,c,down_sources=down_sources) for c in settings.file_config.connectors
            if c.enabled and (only is None or c.key in only)]


def describe_connectors(settings: Settings) -> list[dict]:
    return [dict(key=c.key,kind=c.kind,enabled=c.enabled,notes=c.notes,
                 capabilities=build_one(settings,c).capabilities().model_dump()) for c in settings.file_config.connectors]
