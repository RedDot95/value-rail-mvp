"""Repository functions. Callers own the transaction (session.begin())."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.entities import QuantityObservation
from ..domain.identity import AssetIdentity, ProductIdentity
from ..evidence import EvidenceDraft, content_hash
from ..valuation.models import RuleParams
from .orm import (AlertRow, AssetRow, EvidenceRow, ExecutionResultRow, OfferSnapshotRow, OperatorProfileRow,
                  ProductRow, QuoteRow, RouteEvaluationRow, RuleVersionRow, ScanRunRow, SourceRow)


# ---------- sources / products ----------

def upsert_source(s: Session, *, key: str, name: str, kind: str, role: str,
                  capabilities: dict[str, bool] | None = None, is_synthetic: bool = False) -> SourceRow:
    row = s.scalar(select(SourceRow).where(SourceRow.key == key))
    if row is None:
        row = SourceRow(key=key, name=name, kind=kind, role=role, capabilities=capabilities or {},
                        health="unknown", is_synthetic=is_synthetic, base_url="unknown")
        s.add(row)
        s.flush()
    else:
        row.name, row.kind, row.role = name, kind, role
        row.capabilities = capabilities or row.capabilities
        row.is_synthetic = is_synthetic
    return row


def mark_source_health(s: Session, row: SourceRow, *, ok: bool, now: datetime, error: str | None = None) -> None:
    if ok:
        row.health, row.last_success_at = "ok", now
    else:
        row.health, row.last_error_at, row.last_error = "down", now, error


def get_or_create_product(s: Session, identity: ProductIdentity, *, family: str, now: datetime,
                          is_synthetic: bool) -> ProductRow:
    key = identity.key()
    row = s.scalar(select(ProductRow).where(ProductRow.identity_key == key))
    if row is None:
        row = ProductRow(identity_key=key, face_value=identity.face_value, face_currency=identity.face_currency,
                         region=identity.region, variant=identity.variant, seller=identity.seller,
                         redemption_program=identity.redemption_program, product_family=family,
                         created_at=now, is_synthetic=is_synthetic)
        s.add(row)
        s.flush()
    return row


# ---------- offer snapshots (immutable, versioned) ----------

def _q(obs: QuantityObservation) -> dict[str, str]:
    at = obs.observed_at if obs.observed_at == "unknown" else obs.observed_at.isoformat()
    return {"value": str(obs.value), "at": at, "scope": obs.scope}


def insert_offer_snapshot(s: Session, *, source: SourceRow, product: ProductRow, scan_run_id: int | None,
                          route_key: str, captured_at: datetime, price_amount: Any, price_currency: str,
                          price_text_raw: str, price_includes_fees: bool, fees: list[dict[str, Any]],
                          advertised: QuantityObservation, checkout_confirmed: QuantityObservation,
                          purchased: QuantityObservation, raw: dict[str, Any], is_synthetic: bool,
                          version: int = 1, supersedes_id: int | None = None) -> OfferSnapshotRow:
    a, c, p = _q(advertised), _q(checkout_confirmed), _q(purchased)
    body = dict(source=source.key, product=product.identity_key, captured_at=captured_at.isoformat(),
                price=str(price_amount), currency=price_currency, fees=fees, adv=a, chk=c, pur=p,
                includes_fees=price_includes_fees)
    row = OfferSnapshotRow(
        source_id=source.id, product_id=product.id, scan_run_id=scan_run_id, route_key=route_key,
        version=version, supersedes_id=supersedes_id, captured_at=captured_at, price_amount=price_amount,
        price_currency=price_currency, price_text_raw=price_text_raw, price_includes_fees=price_includes_fees,
        fees=fees, advertised_quantity=a["value"], advertised_quantity_at=a["at"], advertised_quantity_scope=a["scope"],
        checkout_confirmed_quantity=c["value"], checkout_confirmed_quantity_at=c["at"],
        checkout_confirmed_quantity_scope=c["scope"], purchased_quantity=p["value"], purchased_quantity_at=p["at"],
        purchased_quantity_scope=p["scope"], raw=raw, content_hash=content_hash(body), is_synthetic=is_synthetic)
    s.add(row)
    s.flush()
    return row


def correct_offer_snapshot(s: Session, snapshot_id: int, *, reason: str, **changes: Any) -> OfferSnapshotRow:
    """Corrections never modify the original: a new version superseding it is inserted."""
    old = s.get(OfferSnapshotRow, snapshot_id)
    if old is None:
        raise KeyError(snapshot_id)
    cols = {c.key: getattr(old, c.key) for c in OfferSnapshotRow.__table__.columns if c.key not in ("id",)}
    cols.update(changes)
    cols["version"] = old.version + 1
    cols["supersedes_id"] = old.id
    cols["raw"] = {**(old.raw or {}), "correction_reason": reason}
    cols["content_hash"] = content_hash({k: str(v) for k, v in cols.items() if k != "content_hash"})
    row = OfferSnapshotRow(**cols)
    s.add(row)
    s.flush()
    return row


# ---------- assets ----------

def upsert_asset(s: Session, *, symbol: str, chain: str, contract_address: str, name: str = "unknown",
                 decimals: str = "unknown", is_synthetic: bool = False) -> AssetRow:
    """Merge ONLY on (chain, contract). Same ticker on another chain/contract -> separate asset."""
    ident = AssetIdentity(symbol=symbol, chain=chain, contract_address=contract_address)
    chain_n, contract_n = ident.key().split(":", 1)
    if "unknown" in (chain_n, contract_n):
        raise ValueError("asset without known chain+contract cannot be stored as an identity")
    row = s.scalar(select(AssetRow).where(AssetRow.chain == chain_n, AssetRow.contract_address == contract_n))
    if row is None:
        row = AssetRow(symbol=symbol, name=name, chain=chain_n, contract_address=contract_n,
                       decimals=decimals, is_synthetic=is_synthetic)
        s.add(row)
        s.flush()
    return row


# ---------- evidence ----------

def insert_evidence(s: Session, draft: EvidenceDraft, *, subject_ref: str, source: SourceRow | None) -> EvidenceRow:
    row = EvidenceRow(kind=str(draft.kind), source_id=source.id if source else None, subject_ref=subject_ref,
                      captured_at=draft.captured_at, scope=draft.scope, summary=draft.summary, payload=draft.payload,
                      content_hash=content_hash(draft.payload | {"summary": draft.summary}),
                      is_synthetic=draft.is_synthetic)
    s.add(row)
    s.flush()
    return row


def evidence_for_refs(s: Session, refs: Iterable[str]) -> list[EvidenceRow]:
    refs = list(refs)
    if not refs:
        return []
    return list(s.scalars(select(EvidenceRow).where(EvidenceRow.subject_ref.in_(refs)).order_by(EvidenceRow.id)))


# ---------- rule versions (immutable) ----------

def _params_json(p: RuleParams) -> dict[str, Any]:
    return p.model_dump(mode="json")


def add_rule_version(s: Session, params: RuleParams, *, valid_from: datetime, now: datetime,
                     notes: str = "") -> RuleVersionRow:
    pj = _params_json(params)
    row = RuleVersionRow(label=params.label, params=pj, params_hash=content_hash(pj), valid_from=valid_from,
                         created_at=now, notes=notes)
    s.add(row)
    s.flush()
    return row


def active_rule_version(s: Session, at: datetime) -> RuleVersionRow | None:
    return s.scalar(select(RuleVersionRow).where(RuleVersionRow.valid_from <= at)
                    .order_by(RuleVersionRow.valid_from.desc(), RuleVersionRow.id.desc()).limit(1))


def ensure_rule_version(s: Session, params: RuleParams, *, now: datetime, notes: str = "seeded from config") -> RuleVersionRow:
    current = active_rule_version(s, now)
    if current is not None and current.params_hash == content_hash(_params_json(params)):
        return current
    return add_rule_version(s, params, valid_from=now, now=now, notes=notes)


def rule_version_by_label(s: Session, label: str) -> RuleVersionRow | None:
    return s.scalar(select(RuleVersionRow).where(RuleVersionRow.label == label).order_by(RuleVersionRow.id.desc()).limit(1))


def rule_params_of(row: RuleVersionRow) -> RuleParams:
    return RuleParams.model_validate(row.params)


# ---------- quotes ----------

def insert_quote(s: Session, *, kind: str, source: SourceRow, product: ProductRow | None, scan_run_id: int | None,
                 route_key: str, identity: dict[str, Any], quantity: Any, unit_price: Any, currency: str,
                 depth_quantity: Any, fees: list[dict[str, Any]], captured_at: datetime, valid_until: Any,
                 is_synthetic: bool) -> QuoteRow:
    row = QuoteRow(kind=kind, source_id=source.id, product_id=product.id if product else None, scan_run_id=scan_run_id,
                   route_key=route_key, identity=identity, quantity=str(quantity), unit_price=unit_price,
                   currency=currency, depth_quantity=str(depth_quantity), fees=fees, captured_at=captured_at,
                   valid_until=valid_until if valid_until == "unknown" else valid_until.isoformat(),
                   is_synthetic=is_synthetic)
    s.add(row)
    s.flush()
    return row


# ---------- operator profiles ----------

def upsert_operator_profile(s: Session, *, name: str, region: str, capabilities: dict[str, str],
                            max_budget_eur: Any = "unknown", is_synthetic: bool = False) -> OperatorProfileRow:
    row = s.scalar(select(OperatorProfileRow).where(OperatorProfileRow.name == name))
    if row is None:
        row = OperatorProfileRow(name=name, region=region, capabilities=capabilities, max_budget_eur=max_budget_eur,
                                 is_synthetic=is_synthetic)
        s.add(row)
        s.flush()
    else:
        row.region, row.capabilities, row.max_budget_eur = region, capabilities, max_budget_eur
    return row


# ---------- evaluations ----------

def latest_evaluations(s: Session) -> list[RouteEvaluationRow]:
    sub = (select(RouteEvaluationRow.route_key, func.max(RouteEvaluationRow.id).label("mid"))
           .group_by(RouteEvaluationRow.route_key).subquery())
    q = select(RouteEvaluationRow).join(sub, RouteEvaluationRow.id == sub.c.mid).order_by(RouteEvaluationRow.id.desc())
    return list(s.scalars(q))


def latest_evaluation_for(s: Session, route_key: str) -> RouteEvaluationRow | None:
    return s.scalar(select(RouteEvaluationRow).where(RouteEvaluationRow.route_key == route_key)
                    .order_by(RouteEvaluationRow.id.desc()).limit(1))


def latest_scan_runs(s: Session, limit: int = 10) -> list[ScanRunRow]:
    return list(s.scalars(select(ScanRunRow).order_by(ScanRunRow.id.desc()).limit(limit)))


def last_alert_for(s: Session, route_key: str) -> AlertRow | None:
    return s.scalar(select(AlertRow).where(AlertRow.route_key == route_key).order_by(AlertRow.id.desc()).limit(1))


def record_execution_result(s: Session, *, route_evaluation_id: int | None, product_id: int | None,
                            executed_at: datetime, status: str, purchased_quantity: int | str,
                            total_cost_eur: Decimal | str, notes: str, is_synthetic: bool) -> ExecutionResultRow:
    """Manual bookkeeping of a purchase done OUTSIDE the system. The system never buys."""
    if status not in ("executed", "failed"):
        raise ValueError("status must be executed|failed")
    row = ExecutionResultRow(route_evaluation_id=route_evaluation_id, product_id=product_id, executed_at=executed_at,
                             status=status, purchased_quantity=str(purchased_quantity),
                             purchased_quantity_scope="manual_record", total_cost_eur=total_cost_eur, notes=notes,
                             is_synthetic=is_synthetic)
    s.add(row)
    s.flush()
    return row
