"""Provider interface + typed question/answer models for the enrichment layer.

The question/answer shapes mirror the TypeSafe System One API as documented on 2026-10-06
(https://docs.typesafe.ai/api.md, /primitives.md): three question types (choice, noul, score), each with
`instructions` (string/object/array) and `criteria`; independent questions over the SAME state are sent
together in ONE request and evaluated in parallel. Answers are constrained to the supplied options.

Probabilities are floats on purpose: they are model signals, never money. Nothing in this module produces
a monetary value.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

ABSTAIN_SIGNAL = "abstain"
MAX_CHOICE_OPTIONS = 255  # API limit per Choice (docs.typesafe.ai/api.md)
MAX_SCORE_LEVELS = 10     # API limit per Score


class JudgmentKind(StrEnum):
    CHOICE = "choice"
    NOUL = "noul"
    SCORE = "score"


JSONish = str | dict[str, Any] | list[Any]


class Question(BaseModel):
    """One typed question. `id` is ours (never sent to the model as context; answers come back under it)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    kind: JudgmentKind
    instructions: JSONish
    # choice: {option_key: description|None}; score: [level descriptions]; noul: {"true": ..., "false": ...}|None
    criteria: dict[str, Any] | list[Any] | None = None

    @model_validator(mode="after")
    def _check(self) -> "Question":
        if self.kind == JudgmentKind.CHOICE:
            if not isinstance(self.criteria, dict) or not self.criteria:
                raise ValueError(f"{self.id}: choice needs a non-empty criteria map")
            if len(self.criteria) > MAX_CHOICE_OPTIONS:
                raise ValueError(f"{self.id}: choice allows at most {MAX_CHOICE_OPTIONS} options")
        elif self.kind == JudgmentKind.SCORE:
            if not isinstance(self.criteria, list) or not 2 <= len(self.criteria) <= MAX_SCORE_LEVELS:
                raise ValueError(f"{self.id}: score needs 2..{MAX_SCORE_LEVELS} levels")
        elif self.criteria is not None and (not isinstance(self.criteria, dict)
                                            or set(self.criteria) - {"true", "false"}):
            raise ValueError(f"{self.id}: noul criteria may only contain 'true'/'false'")
        return self

    @property
    def options(self) -> tuple[str, ...]:
        return tuple(self.criteria) if self.kind == JudgmentKind.CHOICE and isinstance(self.criteria, dict) else ()

    def to_api(self) -> dict[str, Any]:
        body: dict[str, Any] = {"type": self.kind.value, "instructions": self.instructions}
        if self.criteria is not None:
            body["criteria"] = self.criteria
        return body


class JudgmentRequest(BaseModel):
    """A BATCH of independent questions over one shared state (one API call; TypeSafe runs them in parallel)."""

    model_config = ConfigDict(frozen=True)

    state: JSONish
    questions: tuple[Question, ...]

    @model_validator(mode="after")
    def _unique(self) -> "JudgmentRequest":
        if not self.questions:
            raise ValueError("a judgment request needs at least one question")
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate question ids: {ids}")
        return self

    def question(self, qid: str) -> Question:
        return next(q for q in self.questions if q.id == qid)


class JudgmentResult(BaseModel):
    """Typed answer to one question. `abstained=True` means NO signal (null provider, error, invalid answer)."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    kind: JudgmentKind
    answer: str | None = None          # choice: option key; noul: "yes"/"no" (p >= 0.5); score: nearest level
    probability: float | None = None   # noul: P(yes); choice: P(answer); score: P(nearest level)
    confidence: float | None = None    # choice/score only (noul has none per API)
    score: float | None = None         # score only
    distribution: dict[str, float] | None = None
    provider: str
    model: str
    created_at: datetime
    abstained: bool = False
    abstain_reason: str = ""


def abstain(q: Question, *, provider: str, model: str, created_at: datetime, reason: str) -> JudgmentResult:
    return JudgmentResult(question_id=q.id, kind=q.kind, provider=provider, model=model, created_at=created_at,
                          abstained=True, abstain_reason=reason)


def abstain_all(req: JudgmentRequest, *, provider: str, model: str, created_at: datetime,
                reason: str) -> list[JudgmentResult]:
    return [abstain(q, provider=provider, model=model, created_at=created_at, reason=reason) for q in req.questions]


@runtime_checkable
class JudgmentProvider(Protocol):
    """Contract: `judge` returns exactly one result per question and NEVER raises into the caller.

    On any failure an implementation returns abstain results. Providers must not perform network I/O on
    construction or import.
    """

    name: str

    def judge(self, request: JudgmentRequest) -> list[JudgmentResult]: ...
