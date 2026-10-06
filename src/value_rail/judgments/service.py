"""EnrichmentService: batch the independent questions per offer into ONE request, derive signals in code,
persist them as INFERRED judgments. Purely additive; never touches valuation outputs or the alert outbox.

Network I/O happens outside any DB transaction (same rule as the scan pipeline, D-16). A per-run request
budget ([enrichment].max_requests_per_scan) and a per-offer question cap bound cost. When enrichment is
disabled, `build_enrichment_service` returns None and no provider/client object is constructed at all.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field

from ..domain.timeutil import utcnow
from .base import JudgmentProvider, JudgmentRequest, JudgmentResult, Question, abstain_all
from .null_provider import NullJudgmentProvider
from .questions import (CLASSIFY_INSTRUMENT, FAMILY_ALIASES, LOOKS_LIKE_BLOCK_PAGE, QUESTION_PRIORITY,
                        RESTRICTION_RISK, SELECT_FACE_VALUE, Candidate, classify_instrument,
                        extract_numeric_candidates, looks_like_block_page, resolve_selected_candidate,
                        restriction_risk, select_face_value)
from .safety import ADVISORY_BLOCK, SUSPECTED_BLOCK_PAGE

if TYPE_CHECKING:  # typing only - keeps import of this module free of side effects
    from sqlalchemy.orm import Session, sessionmaker

    from ..connectors.base import DiscoveryItem, NormalizedOffer
    from ..settings import EnrichmentConfig, Settings

log = logging.getLogger("value_rail.judgments")

_DESC_KEYS = ("name", "title", "description", "brand", "sku", "denomination", "region", "availability", "seller")


class OfferContext(BaseModel):
    """Everything the questions may see about one offer. Observed values are inputs, never outputs."""

    model_config = ConfigDict(frozen=True)

    route_key: str
    source_key: str
    source_name: str = ""
    title: str = ""
    description: str = ""
    merchant: str = "unknown"
    region: str = "unknown"
    variant: str = "unknown"
    redemption_program: str = "unknown"
    price_text: str = "unknown"
    observed_family: str = "unknown"
    observed_face_value: Any = "unknown"  # Decimal | "unknown" (observed, for comparison only)
    payload: str = ""
    offer_snapshot_id: int | None = None
    route_evaluation_id: int | None = None
    scan_run_id: int | None = None
    is_synthetic: bool = False


class EnrichmentOutcome(BaseModel):
    context: OfferContext
    results: list[JudgmentResult] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    selected: Candidate | None = None
    signals: dict[str, str] = Field(default_factory=dict)

    @property
    def advisory_block(self) -> bool:
        return self.signals.get(RESTRICTION_RISK) == ADVISORY_BLOCK

    @property
    def selected_face_value(self) -> Decimal | None:
        return self.selected.value if self.selected is not None else None


class EnrichmentRunReport(BaseModel):
    provider: str
    offers_seen: int = 0
    requests: int = 0
    skipped_budget: int = 0
    judgments_persisted: int = 0
    abstained: int = 0
    advisory_blocks: int = 0
    suspected_block_pages: int = 0
    errors: int = 0


def _clip(v: Any, n: int) -> str:
    s = "" if v is None else str(v)
    return s if len(s) <= n else s[:n] + "…"


def context_from_offer(item: "DiscoveryItem", offer: "NormalizedOffer", *, max_chars: int = 4000,
                       offer_snapshot_id: int | None = None, route_evaluation_id: int | None = None,
                       scan_run_id: int | None = None) -> OfferContext:
    raw = offer.raw or {}
    desc = "; ".join(f"{k}: {raw[k]}" for k in _DESC_KEYS if isinstance(raw.get(k), (str, int)) and raw.get(k) != "")
    ident = offer.identity
    try:
        payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        payload = str(raw)
    return OfferContext(
        route_key=item.route_key, source_key=offer.source.key, source_name=offer.source.name,
        title=_clip(item.meta.get("title_de") or item.meta.get("title") or item.route_key, max_chars),
        description=_clip(desc, max_chars), merchant=ident.seller, region=ident.region, variant=ident.variant,
        redemption_program=ident.redemption_program, price_text=_clip(offer.price_text_raw, 200),
        observed_family=item.product_family, observed_face_value=ident.face_value, payload=_clip(payload, max_chars),
        offer_snapshot_id=offer_snapshot_id, route_evaluation_id=route_evaluation_id, scan_run_id=scan_run_id,
        is_synthetic=offer.is_synthetic)


def context_from_snapshot(snap: Any, product: Any, source: Any, *, route_evaluation_id: int | None,
                          max_chars: int = 4000) -> OfferContext:
    """Context from stored rows (OfferSnapshotRow/ProductRow/SourceRow), used by `value-rail enrich` backfill."""
    raw = dict(snap.raw or {})
    raw.pop("identity", None)
    desc = "; ".join(f"{k}: {raw[k]}" for k in _DESC_KEYS if isinstance(raw.get(k), (str, int)) and raw.get(k) != "")
    try:
        payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        payload = str(raw)
    return OfferContext(
        route_key=snap.route_key, source_key=source.key, source_name=source.name, title=_clip(snap.route_key, max_chars),
        description=_clip(desc, max_chars), merchant=product.seller, region=product.region, variant=product.variant,
        redemption_program=product.redemption_program, price_text=_clip(snap.price_text_raw, 200),
        observed_family=product.product_family, observed_face_value=product.face_value, payload=_clip(payload, max_chars),
        offer_snapshot_id=snap.id, route_evaluation_id=route_evaluation_id, scan_run_id=snap.scan_run_id,
        is_synthetic=snap.is_synthetic)


def build_state(ctx: OfferContext, cfg: "EnrichmentConfig", candidates: list[Candidate],
                include_payload: bool) -> dict[str, Any]:
    n = cfg.max_state_chars
    state: dict[str, Any] = {
        "offer": {"title": _clip(ctx.title, n), "description": _clip(ctx.description, n),
                  "merchant": _clip(ctx.merchant, 200), "source": _clip(ctx.source_name or ctx.source_key, 200),
                  "region": ctx.region, "variant": ctx.variant, "redemption_program": ctx.redemption_program,
                  "price_text": _clip(ctx.price_text, 200), "observed_family": ctx.observed_family},
        "compliant_route": {"customer_region": cfg.customer_region, "accepted_regions": list(cfg.accepted_regions)},
    }
    if include_payload:
        state["payload_snippet"] = _clip(ctx.payload, n)
    if candidates:
        state["numeric_candidates"] = {c.option_key: c.describe() for c in candidates}
    return state


class EnrichmentService:
    def __init__(self, provider: JudgmentProvider, cfg: "EnrichmentConfig", *,
                 clock: Callable[[], datetime] = utcnow) -> None:
        self.provider = provider
        self.cfg = cfg
        self.clock = clock
        self.requests_used = 0

    @property
    def provider_name(self) -> str:
        return getattr(self.provider, "name", type(self.provider).__name__)

    def begin_run(self) -> None:
        self.requests_used = 0

    # ---------- request building ----------
    def build_request(self, ctx: OfferContext) -> tuple[JudgmentRequest | None, list[Candidate]]:
        cfg = self.cfg
        candidates = extract_numeric_candidates(
            [("offer.title", ctx.title), ("offer.description", ctx.description), ("offer.price_text", ctx.price_text)],
            limit=cfg.max_face_value_candidates)
        wanted: dict[str, Question] = {RESTRICTION_RISK: restriction_risk(), CLASSIFY_INSTRUMENT: classify_instrument()}
        if ctx.payload.strip():
            wanted[LOOKS_LIKE_BLOCK_PAGE] = looks_like_block_page()
        if candidates:
            wanted[SELECT_FACE_VALUE] = select_face_value(candidates)
        chosen = [wanted[q] for q in QUESTION_PRIORITY if q in wanted][: cfg.max_questions_per_offer]
        if not chosen:
            return None, []
        ids = {q.id for q in chosen}
        if SELECT_FACE_VALUE not in ids:
            candidates = []
        state = build_state(ctx, cfg, candidates, include_payload=LOOKS_LIKE_BLOCK_PAGE in ids)
        return JudgmentRequest(state=state, questions=tuple(chosen)), candidates

    # ---------- signals (decisions live in code) ----------
    def _signal(self, r: JudgmentResult, ctx: OfferContext, selected: Candidate | None) -> str:
        cfg = self.cfg
        if r.abstained:
            return "abstain"
        if r.question_id == RESTRICTION_RISK:
            p = r.probability or 0.0
            if p >= cfg.restriction_block_threshold:
                return ADVISORY_BLOCK
            return "review_restriction" if p >= cfg.restriction_review_threshold else "no_restriction"
        if r.question_id == LOOKS_LIKE_BLOCK_PAGE:
            return SUSPECTED_BLOCK_PAGE if (r.probability or 0.0) >= cfg.block_page_threshold else "looks_like_offer_data"
        if r.question_id == CLASSIFY_INSTRUMENT:
            if (r.confidence or 0.0) < cfg.family_min_confidence:
                return "family_uncertain"
            observed = FAMILY_ALIASES.get(ctx.observed_family)
            if observed is None:
                return "family_hint"
            return "family_consistent" if r.answer == observed else "family_mismatch_hint"
        if r.question_id == SELECT_FACE_VALUE:
            if selected is None:
                return "face_value_none"
            obs = ctx.observed_face_value
            if obs == "unknown" or obs is None:
                return "face_value_selected"
            return "face_value_consistent" if Decimal(obs) == selected.value else "face_value_mismatch_hint"
        return "info"

    # ---------- run ----------
    def enrich(self, ctx: OfferContext) -> EnrichmentOutcome | None:
        """One batched request for one offer. None when the budget is exhausted or nothing to ask."""
        req, candidates = self.build_request(ctx)
        if req is None:
            return None
        if self.requests_used >= self.cfg.max_requests_per_scan:
            return None
        self.requests_used += 1
        try:
            results = self.provider.judge(req)
        except Exception as exc:  # noqa: BLE001 - defence in depth: a provider must not raise, but never trust it
            log.warning("judgment provider %s raised %s; abstaining", self.provider_name, type(exc).__name__)
            results = abstain_all(req, provider=self.provider_name, model="unknown", created_at=self.clock(),
                                  reason=f"provider raised {type(exc).__name__}")
        by_id = {r.question_id: r for r in results if isinstance(r, JudgmentResult)}
        # exactly one result per asked question; anything missing becomes an explicit abstain
        missing = [q for q in req.questions if q.id not in by_id]
        if missing:
            for r in abstain_all(JudgmentRequest(state=req.state, questions=tuple(missing)),
                                 provider=self.provider_name, model="unknown", created_at=self.clock(),
                                 reason="provider returned no result"):
                by_id[r.question_id] = r
        ordered = [by_id[q.id] for q in req.questions]
        selected = resolve_selected_candidate(by_id.get(SELECT_FACE_VALUE), candidates,
                                              min_confidence=self.cfg.face_value_min_confidence)
        signals = {r.question_id: self._signal(r, ctx, selected) for r in ordered}
        return EnrichmentOutcome(context=ctx, results=ordered, candidates=candidates, selected=selected,
                                 signals=signals)

    def persist(self, s: "Session", outcome: EnrichmentOutcome) -> int:
        from ..storage.repo import insert_offer_judgment
        ctx, n = outcome.context, 0
        for r in outcome.results:
            if r.abstained and not self.cfg.persist_abstentions:
                continue
            is_face = r.question_id == SELECT_FACE_VALUE and outcome.selected is not None
            insert_offer_judgment(
                s, route_key=ctx.route_key, source_key=ctx.source_key, question_id=r.question_id, kind=r.kind.value,
                answer=r.answer, probability=r.probability, confidence=r.confidence, score=r.score,
                distribution=r.distribution, signal=outcome.signals.get(r.question_id, "info"),
                abstained=r.abstained, abstain_reason=r.abstain_reason, provider=r.provider, model=r.model,
                created_at=r.created_at, offer_snapshot_id=ctx.offer_snapshot_id,
                route_evaluation_id=ctx.route_evaluation_id, scan_run_id=ctx.scan_run_id,
                selected_value=outcome.selected.value if is_face else None,
                selected_candidate=outcome.selected.evidence() if is_face else None, is_synthetic=ctx.is_synthetic)
            n += 1
        return n

    def run(self, contexts: Iterable[OfferContext], *,
            session_factory: "sessionmaker[Session] | None" = None) -> tuple[EnrichmentRunReport, list[EnrichmentOutcome]]:
        """Enrich contexts; persist when a session factory is given (dry-run otherwise). Never raises."""
        rep = EnrichmentRunReport(provider=self.provider_name)
        outcomes: list[EnrichmentOutcome] = []
        for ctx in contexts:
            rep.offers_seen += 1
            if self.requests_used >= self.cfg.max_requests_per_scan:
                rep.skipped_budget += 1
                continue
            try:
                out = self.enrich(ctx)
            except Exception as exc:  # noqa: BLE001
                rep.errors += 1
                log.warning("enrichment of %s failed: %s", ctx.route_key, type(exc).__name__)
                continue
            if out is None:  # nothing to ask (e.g. max_questions_per_offer = 0)
                continue
            rep.requests += 1
            outcomes.append(out)
            rep.abstained += sum(1 for r in out.results if r.abstained)
            rep.advisory_blocks += int(out.advisory_block)
            rep.suspected_block_pages += int(out.signals.get(LOOKS_LIKE_BLOCK_PAGE) == SUSPECTED_BLOCK_PAGE)
            if session_factory is not None:
                try:
                    with session_factory.begin() as s:
                        rep.judgments_persisted += self.persist(s, out)
                except Exception as exc:  # noqa: BLE001
                    rep.errors += 1
                    log.warning("persisting judgments for %s failed: %s", ctx.route_key, type(exc).__name__)
        if rep.skipped_budget:
            log.info("enrichment budget exhausted: %d offer(s) skipped (max_requests_per_scan=%d)",
                     rep.skipped_budget, self.cfg.max_requests_per_scan)
        return rep, outcomes


def build_provider(settings: "Settings") -> JudgmentProvider:
    """Null unless enabled AND provider=typesafe AND TYPESAFE_API_KEY present. Constructs no HTTP client."""
    cfg = settings.file_config.enrichment
    if cfg.enabled and cfg.provider == "typesafe":
        if settings.typesafe_configured:
            from .typesafe_provider import TypeSafeJudgmentProvider
            return TypeSafeJudgmentProvider(api_key=settings.typesafe_api_key.get_secret_value(),
                                            base_url=cfg.base_url, model=cfg.model, timeout_s=cfg.timeout_seconds,
                                            max_retries=cfg.max_retries)
        log.warning("[enrichment] provider = \"typesafe\" but TYPESAFE_API_KEY is not set -> null provider (no network)")
    return NullJudgmentProvider()


def build_enrichment_service(settings: "Settings") -> EnrichmentService | None:
    """None when [enrichment].enabled is false: the scan path then does nothing at all."""
    cfg = settings.file_config.enrichment
    if not cfg.enabled:
        return None
    return EnrichmentService(build_provider(settings), cfg)


__all__ = ["EnrichmentOutcome", "EnrichmentRunReport", "EnrichmentService", "OfferContext", "build_enrichment_service",
           "build_provider", "build_state", "context_from_offer", "context_from_snapshot"]
