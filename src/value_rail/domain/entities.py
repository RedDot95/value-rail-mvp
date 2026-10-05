"""Domain entities required by the Bauauftrag (minimum fields).

These Pydantic models are the canonical in-memory/API representation. Persistence lives in
`value_rail.storage.orm`. Rules enforced across the code base:
- snapshots are immutable; corrections are new versions (`version`, `supersedes_id`)
- all timestamps are UTC; Europe/Berlin is display-only
- money is Decimal; floats are rejected
- missing required info is the literal "unknown", never null
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import (AlertState, EvidenceKind, PrereqStatus, RouteStatus, ScanStatus, SourceHealth,
                    SourceKind, SourceRole)
from .identity import ProductIdentity
from .money import Dec, MaybeDecimal, MaybeInt, UnknownT


class _Immutable(BaseModel):
    model_config = ConfigDict(frozen=True)


class QuantityObservation(_Immutable):
    """One quantity statement with its own timestamp and scope.

    advertised != checkout-confirmed != purchased. They are never collapsed into one number.
    """

    value: MaybeInt = "unknown"
    observed_at: datetime | UnknownT = "unknown"
    scope: str = "unknown"  # e.g. "listing", "checkout_session", "historical_purchase"


class Source(BaseModel):
    key: str
    name: str
    kind: SourceKind
    role: SourceRole
    base_url: str = "unknown"  # never invented; stays "unknown" until access is verified
    capabilities: dict[str, bool] = Field(default_factory=dict)
    health: SourceHealth = SourceHealth.UNKNOWN
    last_success_at: datetime | UnknownT = "unknown"
    last_error: str | None = None
    is_synthetic: bool = False


class Product(_Immutable):
    identity: ProductIdentity
    product_family: str = "unknown"  # e.g. "bitsa", "paysafecard"
    is_synthetic: bool = False


class OfferSnapshot(_Immutable):
    source_key: str
    product: ProductIdentity
    captured_at: datetime
    price_amount: MaybeDecimal
    price_currency: str  # "unknown" when not provable ("$" alone is NOT USD)
    price_text_raw: str = "unknown"
    price_includes_fees: bool = False
    advertised_quantity: QuantityObservation = QuantityObservation()
    checkout_confirmed_quantity: QuantityObservation = QuantityObservation()
    purchased_quantity: QuantityObservation = QuantityObservation()
    version: int = 1
    supersedes_id: int | None = None
    is_synthetic: bool = False


class Asset(_Immutable):
    symbol: str
    name: str = "unknown"
    chain: str = "unknown"
    contract_address: str = "unknown"
    decimals: MaybeInt = "unknown"
    is_synthetic: bool = False


class Evidence(_Immutable):
    kind: EvidenceKind
    source_key: str
    subject_ref: str  # e.g. "offer_snapshot:12", "quote:4"
    captured_at: datetime
    scope: str = "unknown"
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = "unknown"
    version: int = 1
    supersedes_id: int | None = None
    is_synthetic: bool = False


class RuleVersion(_Immutable):
    label: str
    params: dict[str, Any]
    valid_from: datetime
    notes: str = ""


class Quote(_Immutable):
    kind: str  # "checkout" | "exit" | "fx"
    source_key: str
    product: ProductIdentity | None = None
    quantity: MaybeInt = "unknown"
    unit_price: MaybeDecimal = "unknown"
    currency: str = "unknown"
    depth_quantity: MaybeInt = "unknown"
    fees: list[dict[str, Any]] = Field(default_factory=list)
    captured_at: datetime
    valid_until: datetime | UnknownT = "unknown"
    version: int = 1
    supersedes_id: int | None = None
    is_synthetic: bool = False


class OperatorProfile(BaseModel):
    name: str
    region: str = "unknown"
    capabilities: dict[str, PrereqStatus] = Field(default_factory=dict)  # e.g. {"bitsa_account": "proven"}
    max_budget_eur: MaybeDecimal = "unknown"
    is_synthetic: bool = False


class RouteEvaluation(_Immutable):
    route_key: str
    rule_version_id: int
    evaluated_at: datetime
    status: RouteStatus
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    inputs_hash: str
    engine_version: str
    is_synthetic: bool = False


class ScanRun(BaseModel):
    started_at: datetime
    finished_at: datetime | None = None
    status: ScanStatus = ScanStatus.RUNNING
    trigger: str = "cli"
    sources_ok: list[str] = Field(default_factory=list)
    sources_failed: dict[str, str] = Field(default_factory=dict)
    is_synthetic: bool = False


class Alert(BaseModel):
    event_id: str
    route_key: str
    route_evaluation_id: int
    state: AlertState = AlertState.PENDING
    reason: str
    payload: dict[str, Any]
    attempts: int = 0
    max_attempts: int = 5
    last_error: str | None = None


class ExecutionResult(_Immutable):
    """Manual record of an executed (or failed) purchase. The system never purchases itself."""

    route_evaluation_id: int | None
    executed_at: datetime
    status: RouteStatus  # executed | failed
    purchased_quantity: QuantityObservation
    total_cost_eur: MaybeDecimal = "unknown"
    notes: str = ""
    is_synthetic: bool = False
