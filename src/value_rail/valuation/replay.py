"""Exact replay of a stored evaluation with its stored RuleVersion and stored inputs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..evidence import content_hash
from ..storage.orm import RouteEvaluationRow, RuleVersionRow
from .engine import evaluate_route
from .models import RouteInputs, RuleParams


class ReplayResult(BaseModel):
    evaluation_id: int
    rule_version_id: int
    rule_label: str
    match: bool
    inputs_hash_ok: bool
    engine_version_stored: str
    engine_version_now: str
    diff: dict[str, Any]


def replay_evaluation(s: Session, evaluation_id: int) -> ReplayResult:
    ev = s.get(RouteEvaluationRow, evaluation_id)
    if ev is None:
        raise KeyError(evaluation_id)
    rv = s.get(RuleVersionRow, ev.rule_version_id)
    params = RuleParams.model_validate(rv.params)
    inputs = RouteInputs.model_validate(ev.inputs)
    recomputed = evaluate_route(inputs, params).canonical()
    stored = ev.outputs
    # engine_version is reported separately (engine_version_stored/now); a version bump alone is no diff
    diff = {k: {"stored": stored.get(k), "replayed": recomputed.get(k)}
            for k in sorted(set(stored) | set(recomputed))
            if k != "engine_version" and stored.get(k) != recomputed.get(k)}
    return ReplayResult(evaluation_id=ev.id, rule_version_id=rv.id, rule_label=rv.label, match=not diff,
                        inputs_hash_ok=content_hash(ev.inputs) == ev.inputs_hash,
                        engine_version_stored=ev.engine_version, engine_version_now=recomputed["engine_version"], diff=diff)
