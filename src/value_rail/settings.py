"""Runtime settings (env) + file configuration (TOML)."""

from __future__ import annotations

import tomllib
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT_GUESS = PACKAGE_DIR.parents[1]


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


class RuleConfig(BaseModel):
    label: str = "default"
    price_find_min_discount: Decimal = Decimal("0.25")
    verified_min_edge: Decimal = Decimal("0.10")
    verified_min_profit_eur: Decimal = Decimal("1.00")
    max_quote_age_seconds: int = 900
    max_offer_age_seconds: int = 3600


class AlertConfig(BaseModel):
    sink: str = "log"
    alert_statuses: list[str] = Field(default_factory=lambda: ["price_find", "verified_route"])
    material_price_change_pct: Decimal = Decimal("0.02")
    restock_min_increase: int = 1
    max_attempts: int = 5
    retry_backoff_seconds: int = 60
    log_file: str | None = "data/alerts.log"


class ScanIntervals(BaseModel):
    watchlist_seconds: int = 300
    new_sellers_seconds: int = 1800
    aggregator_seconds: int = 86400
    stale_after_seconds: int = 900


class ConnectorConfig(BaseModel):
    key: str
    kind: str
    enabled: bool = False
    product_family: str | None = None
    notes: str = ""


class FileConfig(BaseModel):
    display: dict[str, Any] = Field(default_factory=lambda: {"timezone": "Europe/Berlin"})
    rules: RuleConfig = Field(default_factory=RuleConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    scan_intervals: ScanIntervals = Field(default_factory=ScanIntervals)
    connectors: list[ConnectorConfig] = Field(default_factory=list)

    @property
    def display_timezone(self) -> str:
        return str(self.display.get("timezone", "Europe/Berlin"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VALUE_RAIL_", env_file=".env", extra="ignore")

    db_path: Path = Path("./data/value_rail.db")
    db_url: str | None = None  # overrides db_path when set (tests use this)
    config_path: Path = _first_existing(Path("./config/default.toml"), REPO_ROOT_GUESS / "config" / "default.toml")
    fixtures_dir: Path = _first_existing(Path("./tests/fixtures"), REPO_ROOT_GUESS / "tests" / "fixtures")
    migrations_dir: Path = _first_existing(Path("./migrations"), REPO_ROOT_GUESS / "migrations")
    log_level: str = "INFO"
    basic_user: str = ""
    basic_password: str = ""
    alert_log_file: str | None = None  # overrides [alerts].log_file (e.g. /data/alerts.log in Docker)

    @property
    def database_url(self) -> str:
        if self.db_url:
            return self.db_url
        return f"sqlite:///{self.db_path}"

    @cached_property
    def file_config(self) -> FileConfig:
        if self.config_path and Path(self.config_path).exists():
            with open(self.config_path, "rb") as fh:
                return FileConfig.model_validate(tomllib.load(fh))
        return FileConfig()

    @property
    def effective_alert_log_file(self) -> str | None:
        return self.alert_log_file or self.file_config.alerts.log_file

    @property
    def auth_enabled(self) -> bool:
        return bool(self.basic_user and self.basic_password)


def get_settings(**overrides: Any) -> Settings:
    return Settings(**overrides)
