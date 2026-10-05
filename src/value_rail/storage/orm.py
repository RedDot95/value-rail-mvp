"""ORM tables for all Bauauftrag entities.

Immutable tables (offer_snapshots, evidence, rule_versions, quotes, route_evaluations, products,
execution_results) reject UPDATE/DELETE both via an ORM guard and via SQLite triggers created in the
initial migration. Corrections are new rows with version+1 and supersedes_id.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .types import DecimalText, JSONText, UTCDateTime


class Base(DeclarativeBase):
    pass


class ImmutableRecordError(RuntimeError):
    pass


class SourceRow(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(40))
    base_url: Mapped[str] = mapped_column(String(500), default="unknown")
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    health: Mapped[str] = mapped_column(String(20), default="unknown")
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class ProductRow(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identity_key: Mapped[str] = mapped_column(String(500), unique=True)
    face_value: Mapped[Any] = mapped_column(DecimalText)
    face_currency: Mapped[str] = mapped_column(String(10))
    region: Mapped[str] = mapped_column(String(50))
    variant: Mapped[str] = mapped_column(String(200))
    seller: Mapped[str] = mapped_column(String(200))
    redemption_program: Mapped[str] = mapped_column(String(200))
    product_family: Mapped[str] = mapped_column(String(100), default="unknown")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class ScanRunRow(Base):
    __tablename__ = "scan_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    trigger: Mapped[str] = mapped_column(String(40))
    sources_ok: Mapped[list[str]] = mapped_column(JSONText, default=list)
    sources_failed: Mapped[dict[str, str]] = mapped_column(JSONText, default=dict)
    items_seen: Mapped[int] = mapped_column(Integer, default=0)
    evaluations_created: Mapped[int] = mapped_column(Integer, default=0)
    alerts_enqueued: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class OfferSnapshotRow(Base):
    __tablename__ = "offer_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    scan_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"), nullable=True)
    route_key: Mapped[str] = mapped_column(String(200), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("offer_snapshots.id"), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime)
    price_amount: Mapped[Any] = mapped_column(DecimalText)
    price_currency: Mapped[str] = mapped_column(String(10))
    price_text_raw: Mapped[str] = mapped_column(String(200), default="unknown")
    price_includes_fees: Mapped[bool] = mapped_column(Boolean, default=False)
    fees: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    advertised_quantity: Mapped[str] = mapped_column(String(20), default="unknown")
    advertised_quantity_at: Mapped[str] = mapped_column(String(40), default="unknown")
    advertised_quantity_scope: Mapped[str] = mapped_column(String(60), default="unknown")
    checkout_confirmed_quantity: Mapped[str] = mapped_column(String(20), default="unknown")
    checkout_confirmed_quantity_at: Mapped[str] = mapped_column(String(40), default="unknown")
    checkout_confirmed_quantity_scope: Mapped[str] = mapped_column(String(60), default="unknown")
    purchased_quantity: Mapped[str] = mapped_column(String(20), default="unknown")
    purchased_quantity_at: Mapped[str] = mapped_column(String(40), default="unknown")
    purchased_quantity_scope: Mapped[str] = mapped_column(String(60), default="unknown")
    raw: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class AssetRow(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("chain", "contract_address", name="uq_asset_chain_contract"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200), default="unknown")
    chain: Mapped[str] = mapped_column(String(60))
    contract_address: Mapped[str] = mapped_column(String(200))
    decimals: Mapped[str] = mapped_column(String(10), default="unknown")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    subject_ref: Mapped[str] = mapped_column(String(100), index=True)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime)
    scope: Mapped[str] = mapped_column(String(60), default="unknown")
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class RuleVersionRow(Base):
    __tablename__ = "rule_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    params: Mapped[dict[str, Any]] = mapped_column(JSONText)
    params_hash: Mapped[str] = mapped_column(String(64))
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    notes: Mapped[str] = mapped_column(Text, default="")


class QuoteRow(Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # checkout | exit | fx
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    scan_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"), nullable=True)
    route_key: Mapped[str] = mapped_column(String(200), index=True)
    identity: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    quantity: Mapped[str] = mapped_column(String(20), default="unknown")
    unit_price: Mapped[Any] = mapped_column(DecimalText)
    currency: Mapped[str] = mapped_column(String(10))
    depth_quantity: Mapped[str] = mapped_column(String(20), default="unknown")
    fees: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime)
    valid_until: Mapped[str] = mapped_column(String(40), default="unknown")
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("quotes.id"), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class OperatorProfileRow(Base):
    __tablename__ = "operator_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    region: Mapped[str] = mapped_column(String(50), default="unknown")
    capabilities: Mapped[dict[str, str]] = mapped_column(JSONText, default=dict)
    max_budget_eur: Mapped[Any] = mapped_column(DecimalText, default="unknown")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class RouteEvaluationRow(Base):
    __tablename__ = "route_evaluations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_key: Mapped[str] = mapped_column(String(200), index=True)
    scan_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"), nullable=True)
    rule_version_id: Mapped[int] = mapped_column(ForeignKey("rule_versions.id"))
    operator_profile_id: Mapped[int | None] = mapped_column(ForeignKey("operator_profiles.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(20), index=True)
    discount: Mapped[Any] = mapped_column(DecimalText)
    profit_eur: Mapped[Any] = mapped_column(DecimalText)
    edge: Mapped[Any] = mapped_column(DecimalText)
    evaluated_quantity: Mapped[str] = mapped_column(String(20), default="unknown")
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONText)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSONText)
    inputs_hash: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(20))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class AlertRow(Base):
    """Alert outbox. Written in the SAME transaction as its RouteEvaluation."""

    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)
    route_key: Mapped[str] = mapped_column(String(200), index=True)
    route_evaluation_id: Mapped[int] = mapped_column(ForeignKey("route_evaluations.id"))
    state: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(String(60))
    sink: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[dict[str, Any]] = mapped_column(JSONText)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONText)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class ExecutionResultRow(Base):
    """Manual record only - the system never executes purchases."""

    __tablename__ = "execution_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("route_evaluations.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(20))  # executed | failed
    purchased_quantity: Mapped[str] = mapped_column(String(20), default="unknown")
    purchased_quantity_scope: Mapped[str] = mapped_column(String(60), default="unknown")
    total_cost_eur: Mapped[Any] = mapped_column(DecimalText, default="unknown")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class SchedulerLockRow(Base):
    """DB lease preventing overlapping scheduler runs (one holder per lock name; expires on crash)."""

    __tablename__ = "scheduler_locks"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner: Mapped[str] = mapped_column(String(200))
    acquired_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class JobStateRow(Base):
    """Persistent per-job scheduler state (survives restarts; drives bounded catch-up + /healthz)."""

    __tablename__ = "job_states"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    connector: Mapped[str] = mapped_column(String(100))
    interval_seconds: Mapped[int] = mapped_column(Integer)
    next_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(30), default="never_run")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_scan_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    runs_total: Mapped[int] = mapped_column(Integer, default=0)
    skipped_catchup_total: Mapped[int] = mapped_column(Integer, default=0)


class SellerOfferRow(Base):
    """Current state of one seller offer on a watched product page (mutable tracking table).

    The immutable price history lives in offer_snapshots; this table only answers "is this seller offer
    new / still there / gone?" for new-seller detection.
    """

    __tablename__ = "seller_offers"
    __table_args__ = (UniqueConstraint("source_key", "page_url", "offer_key", name="uq_seller_offer"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100))
    page_url: Mapped[str] = mapped_column(String(500))
    offer_key: Mapped[str] = mapped_column(String(300))
    seller: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(40), default="unknown")
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_price: Mapped[str] = mapped_column(String(40), default="unknown")
    currency: Mapped[str] = mapped_column(String(10), default="unknown")
    last_quantity: Mapped[str] = mapped_column(String(40), default="unknown")
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SellerOfferEventRow(Base):
    """Append-only log: baseline / new_seller_offer / price_change / gone / returned."""

    __tablename__ = "seller_offer_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    scan_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_key: Mapped[str] = mapped_column(String(100))
    page_url: Mapped[str] = mapped_column(String(500))
    offer_key: Mapped[str] = mapped_column(String(300))
    seller: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    old_price: Mapped[str] = mapped_column(String(40), default="")
    new_price: Mapped[str] = mapped_column(String(40), default="")
    currency: Mapped[str] = mapped_column(String(10), default="unknown")


IMMUTABLE_TABLES = ("products", "offer_snapshots", "evidence", "rule_versions", "quotes",
                    "route_evaluations", "execution_results")
IMMUTABLE_MODELS = (ProductRow, OfferSnapshotRow, EvidenceRow, RuleVersionRow, QuoteRow,
                    RouteEvaluationRow, ExecutionResultRow)


@event.listens_for(Session, "before_flush")
def _guard_immutable(session: Session, flush_context, instances) -> None:
    for obj in list(session.dirty):
        if isinstance(obj, IMMUTABLE_MODELS) and session.is_modified(obj, include_collections=False):
            raise ImmutableRecordError(f"{type(obj).__name__} is immutable; create a new version instead")
    for obj in list(session.deleted):
        if isinstance(obj, IMMUTABLE_MODELS):
            raise ImmutableRecordError(f"{type(obj).__name__} is immutable; deletion not allowed")


def dec_or_unknown(v: Any) -> Any:
    return "unknown" if v is None or v == "unknown" else Decimal(v)
