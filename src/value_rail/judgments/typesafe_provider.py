"""TypeSafe System One provider (HTTP API via the project's SSRF-safe stdlib client).

API shape verified against the live docs on 2026-10-06 (docs/sources.md "TypeSafe"):
- POST {base_url}/v1/systemone, headers `Authorization: Bearer <TYPESAFE_API_KEY>`, `Content-Type: application/json`
- body  {"state": <str|object|array>, "model": "jev-latest", "questions": {<id>: {"type", "instructions", "criteria"}}}
- reply {"model": "jev-1.13.0", "answers": {<id>: {...}}, "usage": {...}}
    noul   -> {"type": "noul", "noul": 0.95}
    choice -> {"type": "choice", "choice": "<option>", "probabilities": {...}, "confidence": 0.81}
    score  -> {"type": "score", "score": 1.05, "legend": {...}, "probabilities": {"0": ...}, "confidence": 0.92}
- errors 401 / 422 / 429 / 529 (Overloaded); live probe 2026-10-06: a POST without key answers
  403 {"detail": {"error_type": "authentication_error", ...}} - both are handled as auth failure -> abstain

Why not the official `typesafe-sdk` (0.7.2 on PyPI, maintained): it ships its own httpx2 transport + tenacity
retries, which would bypass `net/http_safe.py` (host allowlist, public-IP pinning, no auto-redirects, body
limit) and add three runtime dependencies to a stdlib-only network stack (D-26). The documented HTTP surface is
one endpoint, so we call it directly. See docs/decisions.md D-42.

Robustness: `judge` never raises. Any error/timeout/invalid answer -> abstain results + one warning log line
(exception class + sanitised message; the API key is never logged, printed or put into results).
The HTTP client is constructed lazily on the first call (no network/client objects at import or construction).
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlsplit

from ..domain.timeutil import utcnow
from ..net.http_safe import PolitenessPolicy, SafeHttpClient
from .base import JudgmentKind, JudgmentRequest, JudgmentResult, Question, abstain, abstain_all

log = logging.getLogger("value_rail.judgments")

ENDPOINT_PATH = "/v1/systemone"
SOURCE_KEY = "typesafe-api"


def _prob(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) and 0.0 <= f <= 1.0 else None


class TypeSafeJudgmentProvider:
    name = "typesafe"

    def __init__(self, *, api_key: str, base_url: str = "https://api.typesafe.ai", model: str = "jev-latest",
                 timeout_s: float = 10.0, max_retries: int = 1,
                 http_factory: Callable[[], SafeHttpClient] | None = None,
                 clock: Callable[[], datetime] = utcnow) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("TypeSafe provider needs TYPESAFE_API_KEY")
        parts = urlsplit(base_url)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError("TypeSafe base_url must be an https URL")
        self.__key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.host = parts.hostname.lower()
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._http_factory = http_factory
        self._http: SafeHttpClient | None = None  # lazy
        self._clock = clock

    def __repr__(self) -> str:  # never expose the key
        return f"TypeSafeJudgmentProvider(base_url={self.base_url!r}, model={self.model!r}, key=***)"

    # ---------- transport ----------
    def _client(self) -> SafeHttpClient:
        if self._http is None:
            if self._http_factory is not None:
                self._http = self._http_factory()
            else:
                # An authenticated first-party API, not a crawl: no robots.txt fetch, no 5 s politeness gap
                # (documented limits: 80 req/s). 429 is never retried by SafeHttpClient; 5xx/529 at most max_retries.
                self._http = SafeHttpClient(
                    source_key=SOURCE_KEY, allowed_hosts={self.host}, connect_timeout_s=self.timeout_s,
                    max_bytes=1_000_000, respect_robots=False,
                    policy=PolitenessPolicy(min_interval_s=0.0, jitter_s=0.0, max_retries=self.max_retries,
                                            backoff_base_s=1.0, backoff_max_s=5.0))
        return self._http

    def _sanitise(self, text: str) -> str:
        return text.replace(self.__key, "***")[:300]

    # ---------- public ----------
    def judge(self, request: JudgmentRequest) -> list[JudgmentResult]:
        now = self._clock()
        try:
            payload = {"state": request.state, "model": self.model,
                       "questions": {q.id: q.to_api() for q in request.questions}}
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
            res = self._client().post_json_authorized(self.base_url + ENDPOINT_PATH, body, bearer_token=self.__key)
            data = json.loads(res.body.decode("utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
                raise ValueError("response without an 'answers' object")
        except Exception as exc:  # noqa: BLE001 - contract: never raise into the scan path
            st = getattr(exc, "http_status", None)
            if st in (401, 403):  # live API answers 403 authentication_error without a key (docs list 401)
                reason = f"HTTP {st}: TypeSafe authentication failed (check TYPESAFE_API_KEY)"
            else:
                reason = f"{type(exc).__name__}: {self._sanitise(str(exc))}"
            log.warning("typesafe enrichment failed; abstaining for %d question(s) (%s)", len(request.questions), reason)
            return abstain_all(request, provider=self.name, model=self.model, created_at=now, reason=reason)
        model = str(data.get("model") or self.model)[:60]
        answers = data["answers"]
        return [self._parse(q, answers.get(q.id), model=model, now=now) for q in request.questions]

    # ---------- parsing (strict: anything off-schema -> abstain) ----------
    def _parse(self, q: Question, a: Any, *, model: str, now: datetime) -> JudgmentResult:
        def bad(reason: str) -> JudgmentResult:
            return abstain(q, provider=self.name, model=model, created_at=now, reason=f"invalid answer: {reason}")

        if not isinstance(a, dict):
            return bad("missing")
        if a.get("type") != q.kind.value:
            return bad(f"type {a.get('type')!r} != {q.kind.value!r}")
        common = dict(question_id=q.id, kind=q.kind, provider=self.name, model=model, created_at=now)
        if q.kind == JudgmentKind.NOUL:
            p = _prob(a.get("noul"))
            if p is None:
                return bad("noul not a probability")
            return JudgmentResult(**common, answer="yes" if p >= 0.5 else "no", probability=p)
        probs_raw = a.get("probabilities")
        dist: dict[str, float] = {}
        if isinstance(probs_raw, dict):
            for k, v in probs_raw.items():
                pv = _prob(v)
                if pv is None:
                    return bad("probability out of range")
                dist[str(k)] = pv
        conf = _prob(a.get("confidence"))
        if q.kind == JudgmentKind.CHOICE:
            choice = a.get("choice")
            if not isinstance(choice, str) or choice not in q.options:
                return bad("choice outside the supplied options")
            if set(dist) - set(q.options):
                return bad("probabilities for unknown options")
            return JudgmentResult(**common, answer=choice, probability=dist.get(choice), confidence=conf,
                                  distribution=dist or None)
        # score
        levels = len(q.criteria or [])
        sc = a.get("score")
        if isinstance(sc, bool) or not isinstance(sc, (int, float)) or not math.isfinite(float(sc)) \
                or not 0 <= float(sc) <= levels - 1:
            return bad("score outside the level range")
        if set(dist) - {str(i) for i in range(levels)}:
            return bad("probabilities for unknown levels")
        nearest = str(int(round(float(sc))))
        return JudgmentResult(**common, answer=nearest, probability=dist.get(nearest), confidence=conf,
                              score=float(sc), distribution=dist or None)
