"""Decide whether an evaluation produces a NEW alert event.

- identical repeated scan            -> no new event (and the stable event_id is unique in the outbox)
- status change                       -> new event
- material all-in price change >= pct -> new event
- restock (0/unknown -> >0, or +N)    -> new event
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from ..domain.money import is_unknown
from ..settings import AlertConfig
from ..valuation.models import EvaluationResult


class AlertDecision(BaseModel):
    enqueue: bool
    reason: str
    event_id: str | None = None
    fingerprint: dict[str, Any] = {}


def _qty(result: EvaluationResult) -> str:
    for v in (result.evaluated_quantity, result.proven_quantity, result.advertised_quantity):
        if not is_unknown(v):
            return str(v)
    return "unknown"


def fingerprint(result: EvaluationResult) -> dict[str, Any]:
    return {
        "status": str(result.status),
        "unit_all_in_eur": str(result.unit_all_in_eur),
        "available_quantity": _qty(result),
        "advertised_quantity": str(result.advertised_quantity),
        "price_basis": str(result.price_basis_offer_ref).split(":")[0],
        "rule_label": result.rule_label,
    }


def make_event_id(route_key: str, fp: dict[str, Any], previous_event_id: str | None) -> str:
    # Chained on the previous event so A -> B -> A produces a fresh (but still deterministic) id.
    blob = json.dumps({"route_key": route_key, "fp": fp, "prev": previous_event_id or ""}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def _dec(v: str) -> Decimal | None:
    return None if is_unknown(v) else Decimal(v)


def _int(v: str) -> int | None:
    return None if is_unknown(v) else int(v)


def decide(result: EvaluationResult, previous_fp: dict[str, Any] | None, previous_event_id: str | None,
           cfg: AlertConfig) -> AlertDecision:
    fp = fingerprint(result)
    if str(result.status) not in cfg.alert_statuses:
        return AlertDecision(enqueue=False, reason=f"status_not_alertable:{result.status}", fingerprint=fp)
    eid = make_event_id(result.route_key, fp, previous_event_id)
    if previous_fp is None:
        return AlertDecision(enqueue=True, reason="new", event_id=eid, fingerprint=fp)
    if previous_fp.get("status") != fp["status"]:
        return AlertDecision(enqueue=True, reason="status_change", event_id=eid, fingerprint=fp)
    old_p, new_p = _dec(previous_fp.get("unit_all_in_eur", "unknown")), _dec(fp["unit_all_in_eur"])
    if old_p is not None and new_p is not None and old_p > 0:
        if abs(new_p - old_p) / old_p >= cfg.material_price_change_pct:
            return AlertDecision(enqueue=True, reason="material_price_change", event_id=eid, fingerprint=fp)
    old_q, new_q = _int(previous_fp.get("advertised_quantity", "unknown")), _int(fp["advertised_quantity"])
    if new_q is not None and new_q > 0:
        if old_q is None or old_q == 0 or new_q - old_q >= cfg.restock_min_increase:
            if old_q != new_q:
                return AlertDecision(enqueue=True, reason="restock", event_id=eid, fingerprint=fp)
    return AlertDecision(enqueue=False, reason="duplicate_or_immaterial", fingerprint=fp)
