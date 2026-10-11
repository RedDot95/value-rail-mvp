"""Runtime settings (env) + file configuration (TOML)."""

from __future__ import annotations

import tomllib
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .domain.enums import PrereqStatus
from .domain.money import MaybeDecimal, is_unknown

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT_GUESS = PACKAGE_DIR.parents[1]


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


class RuleConfig(BaseModel):
    evaluation_mode: Literal["route", "screener"] = "route"
    screener_fx_max_age_seconds: int = 345600
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
    kind: Literal["scan", "backup"] = "scan"
    connector: str = ""  # scan jobs: key of a [[connectors]] entry (must be enabled); backup jobs: unused
    interval_seconds: int = 300
    enabled: bool = False
    options: dict[str, Any] = Field(default_factory=dict)  # passed to Connector.configure_for_job (e.g. tiers)
    min_interval_seconds: int = 60  # floor; a job can never run more often than this


class SchedulerConfig(BaseModel):
    tick_seconds: int = Field(default=15, gt=0)
    lock_ttl_seconds: int = Field(default=900, gt=0)  # renewed during jobs; expires after a crash
    max_catchup_runs: int = 1  # after downtime a due job runs at most this many times, never a backlog storm
    heartbeat_file: str = "data/heartbeat.json"
    stale_factor: int = 3  # /healthz: job stale if last success older than stale_factor * interval


class EnrichmentConfig(BaseModel):
    """Optional model-judgment ENRICHMENT/SAFETY layer (docs/decisions.md D-42). OFF by default.

    Judgments are inferred hints only: they never enter the Decimal valuation math, never enqueue an alert and
    never trigger any purchase/checkout/account action or any bypass. Provider resolves to "null" (no network)
    unless `enabled = true`, `provider = "typesafe"` AND TYPESAFE_API_KEY is set.
    """

    enabled: bool = False
    provider: Literal["null", "typesafe"] = "null"
    base_url: str = "https://api.typesafe.ai"  # docs.typesafe.ai/api: POST /v1/systemone
    model: str = "jev-latest"  # alias; the versioned id that answered (e.g. jev-1.13.0) is stored per judgment
    timeout_seconds: float = 10.0
    max_retries: int = 1  # network errors / 5xx (incl. 529 Overloaded) only; 429 is never retried
    max_questions_per_offer: int = Field(default=4, ge=0, le=16)
    max_requests_per_scan: int = Field(default=50, ge=0)  # budget: one batched request per offer
    max_state_chars: int = Field(default=4000, ge=200)  # every string in the state is truncated to this
    max_face_value_candidates: int = Field(default=20, ge=1, le=254)  # Choice allows <= 255 options (+ "none")
    persist_abstentions: bool = False  # abstain rows carry no signal; keep the table lean by default
    show_in_ui: bool = True  # detail page "Inferred (Modell)" card (only while enabled)
    # code-side thresholds (the model returns probabilities; decisions are made here, in code)
    restriction_block_threshold: float = Field(default=0.8, ge=0, le=1)
    restriction_review_threshold: float = Field(default=0.5, ge=0, le=1)
    block_page_threshold: float = Field(default=0.8, ge=0, le=1)
    family_min_confidence: float = Field(default=0.7, ge=0, le=1)
    face_value_min_confidence: float = Field(default=0.8, ge=0, le=1)
    # the compliant redemption route the restriction question is judged against
    customer_region: str = "DE"
    accepted_regions: list[str] = Field(default_factory=lambda: ["DE", "EEA", "EU", "Europe", "global"])


class OperatorProof(BaseModel):
    status: PrereqStatus = PrereqStatus.UNKNOWN
    evidence_ref: str = "unknown"

    @model_validator(mode="after")
    def require_proof(self):
        if self.status == PrereqStatus.PROVEN and (not self.evidence_ref.strip() or is_unknown(self.evidence_ref.strip())):
            raise ValueError("a proven real prerequisite needs an evidence_ref")
        return self


class OperatorConfig(BaseModel):
    name: str
    region: str = "DE"
    max_budget_eur: MaybeDecimal = "unknown"
    capabilities: dict[str, OperatorProof] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def real_name(cls, value):
        value = value.strip()
        if not value or value.upper().startswith("SYNTHETIC"):
            raise ValueError("real operator name must be nonempty and distinct from SYNTHETIC profiles")
        return value


class ScopeConfig(BaseModel):
    allowed_source_keys: list[str] = Field(default_factory=list)
    enabled: bool = False  # production enables the liquid-candidate catalogue; fixtures remain unrestricted


class FileConfig(BaseModel):
    display: dict[str, Any] = Field(default_factory=lambda: {"timezone": "Europe/Berlin"})
    rules: RuleConfig = Field(default_factory=RuleConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    scan_intervals: ScanIntervals = Field(default_factory=ScanIntervals)
    connectors: list[ConnectorConfig] = Field(default_factory=list)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    jobs: list[JobConfig] = Field(default_factory=list)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)
    operator: OperatorConfig | None = None  # real prerequisites are opt-in and require evidence
    scope: ScopeConfig = Field(default_factory=ScopeConfig)

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
    backup_dir: Path = Path("./data/backups")
    backup_keep: int = 14  # newest N backups are kept (daily job -> two weeks)
    # Telegram is OFF unless BOTH are set (and "telegram" is listed in [alerts].sink).
    telegram_bot_token: str = Field(default="", validation_alias=AliasChoices("VALUE_RAIL_TELEGRAM_BOT_TOKEN",
                                                                              "TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = Field(default="", validation_alias=AliasChoices("VALUE_RAIL_TELEGRAM_CHAT_ID",
                                                                            "TELEGRAM_CHAT_ID"))

    # TypeSafe enrichment key (docs/decisions.md D-42). SecretStr: never shown in repr/diagnose/logs.
    typesafe_api_key: SecretStr = Field(default=SecretStr(""), validation_alias=AliasChoices(
        "VALUE_RAIL_TYPESAFE_API_KEY", "TYPESAFE_API_KEY"))

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
    def typesafe_configured(self) -> bool:
        return bool(self.typesafe_api_key.get_secret_value().strip())

    @property
    def enrichment_provider_effective(self) -> str:
        """`typesafe` only if enrichment is enabled, the provider is typesafe AND a key is present; else `null`."""
        cfg = self.file_config.enrichment
        if cfg.enabled and cfg.provider == "typesafe" and self.typesafe_configured:
            return "typesafe"
        return "null"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.basic_user and self.basic_password)


def get_settings(**overrides: Any) -> Settings:
    return Settings(**overrides)
