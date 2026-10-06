"""Transactional outbox: called inside the evaluation's transaction."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..domain.enums import STATUS_LABEL_DE, AlertState
from ..domain.money import fmt_eur, fmt_pct
from ..settings import AlertConfig
from ..storage.orm import AlertRow, RouteEvaluationRow
from ..storage.repo import last_alert_for
from ..valuation.models import EvaluationResult
from .policy import AlertDecision, decide


def build_payload(event_id: str, ev: RouteEvaluationRow, result: EvaluationResult, reason: str) -> dict:
    return {
        "event_id": event_id,
        "reason": reason,
        "route_key": result.route_key,
        "route_evaluation_id": ev.id,
        "status": str(result.status),
        "status_de": STATUS_LABEL_DE[result.status],
        "evaluated_at_utc": ev.evaluated_at.isoformat(),
        "discount": str(result.discount),
        "unit_all_in_eur": str(result.unit_all_in_eur),
        "face_value_reference_eur": str(result.face_value_reference_eur),
        "profit_eur": str(result.profit_eur),
        "edge": str(result.edge),
        "evaluated_quantity": str(result.evaluated_quantity),
        "missing_evidence": result.missing_evidence,
        "summary_de": (f"{STATUS_LABEL_DE[result.status]}: {result.route_key} - Rabatt {fmt_pct(result.discount)}, "
                       f"all-in {fmt_eur(result.unit_all_in_eur)}, Profit {fmt_eur(result.profit_eur)}"),
        "synthetic": ev.is_synthetic,
    }


def enqueue_if_needed(s: Session, ev: RouteEvaluationRow, result: EvaluationResult, cfg: AlertConfig,
                      now: datetime) -> tuple[AlertDecision, AlertRow | None]:
    prev = last_alert_for(s, result.route_key)
    # A suppressed stale notification must not silence a later freshly proven route.
    # Keep the event chain so the replacement still has a unique, deterministic ID.
    previous_fp = prev.fingerprint if prev and prev.state != AlertState.SUPPRESSED.value else None
    decision = decide(result, previous_fp, prev.event_id if prev else None, cfg)
    if not decision.enqueue:
        return decision, None
    if s.query(AlertRow).filter(AlertRow.event_id == decision.event_id).first() is not None:
        return AlertDecision(enqueue=False, reason="event_id_exists", fingerprint=decision.fingerprint), None
    row = AlertRow(event_id=decision.event_id, route_key=result.route_key, route_evaluation_id=ev.id,
                   state=AlertState.PENDING.value, reason=decision.reason, sink=cfg.sink,
                   fingerprint=decision.fingerprint, payload=build_payload(decision.event_id, ev, result, decision.reason),
                   created_at=now, attempts=0, max_attempts=cfg.max_attempts, next_attempt_at=now,
                   is_synthetic=ev.is_synthetic)
    s.add(row)
    s.flush()
    return decision, row
