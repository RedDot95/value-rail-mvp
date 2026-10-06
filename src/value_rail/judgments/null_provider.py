"""Default provider: explicit no-signal ("abstain") for every question. No network, no key, no state."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from ..domain.timeutil import utcnow
from .base import JudgmentRequest, JudgmentResult, abstain_all


class NullJudgmentProvider:
    name = "null"
    model = "none"

    def __init__(self, *, clock: Callable[[], datetime] = utcnow, reason: str = "null provider (enrichment off)") -> None:
        self._clock = clock
        self._reason = reason

    def judge(self, request: JudgmentRequest) -> list[JudgmentResult]:
        return abstain_all(request, provider=self.name, model=self.model, created_at=self._clock(),
                           reason=self._reason)
