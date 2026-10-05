"""Runtime settings (env) + file configuration (TOML)."""

from __future__ import annotations

import tomllib
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, Field
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
    exit_rules: list[dict[str, Any]] = Field(default_factory=list)  # validated as valuation.models.ExitRule


class AlertConfig(BaseModel):
    sink: str = "log"
    alert_statuses: list[str] = Field(default_factory=lambda: ["price_find", "verified_route"])
    material_price_change_pct: Decimal = Decimal("0.02")
    restock_min_increase: int = 1
    max_attempts: int = 5
    retry_backoff_seconds: int = 60
    log_file: str | None = "data/alerts.log"
    telegram_send_synthetic: bool = False


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
    options: dict[str, Any] = Field(default_factory=dict)


class JobConfig(BaseModel):
    name: str
    connector: str  # key of a [[connectors]] entry (must be enabled)
    interval_seconds: int = 300
    enabled: bool = False


class SchedulerConfig(BaseModel):
    tick_seconds: int = 15
    lock_ttl_seconds: int = 900  # a crashed holder's lock expires after this
    max_catchup_runs: int = 1  # after downtime a due job runs at most this many times, never a backlog storm
    heartbeat_file: str = "data/heartbeat.json"
    stale_factor: int = 3  # /healthz: job stale if last success older than stale_factor * interval


class FileConfig(BaseModel):
    display: dict[str, Any] = Field(default_factory=lambda: {"timezone": "Europe/Berlin"})
    rules: RuleConfig = Field(default_factory=RuleConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    scan_intervals: ScanIntervals = Field(default_factory=ScanIntervals)
    connectors: list[ConnectorConfig] = Field(default_factory=list)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    jobs: list[JobConfig] = Field(default_factory=list)

    @property
    def display_timezone(self) -> str:
        return str(self.display.get("timezone", "Europe/Berlin"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VALUE_RAIL_", env_file=".env", extra="ignore",
                                      validate_by_name=True, validate_by_alias=True)

    db_path: Path = Path("./data/value_rail.db")
    db_url: str | None = None  # overrides db_path when set (tests use this)
    config_path: Path = _first_existing(Path("./config/default.toml"), REPO_ROOT_GUESS / "config" / "default.toml")
    fixtures_dir: Path = _first_existing(Path("./tests/fixtures"), REPO_ROOT_GUESS / "tests" / "fixtures")
    migrations_dir: Path = _first_existing(Path("./migrations"), REPO_ROOT_GUESS / "migrations")
    log_level: str = "INFO"
    basic_user: str = ""
    basic_password: str = ""
    alert_log_file: str | None = None  # overrides [alerts].log_file (e.g. /data/alerts.log in Docker)
    heartbeat_file: str | None = None  # overrides [scheduler].heartbeat_file
    # Telegram is OFF unless BOTH are set (and "telegram" is listed in [alerts].sink).
    telegram_bot_token: str = Field(default="", validation_alias=AliasChoices("VALUE_RAIL_TELEGRAM_BOT_TOKEN",
                                                                              "TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = Field(default="", validation_alias=AliasChoices("VALUE_RAIL_TELEGRAM_CHAT_ID",
                                                                            "TELEGRAM_CHAT_ID"))

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
    def effective_heartbeat_file(self) -> str:
        return self.heartbeat_file or self.file_config.scheduler.heartbeat_file

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token.strip() and self.telegram_chat_id.strip())

    @property
    def auth_enabled(self) -> bool:
        return bool(self.basic_user and self.basic_password)


def get_settings(**overrides: Any) -> Settings:
    return Settings(**overrides)
