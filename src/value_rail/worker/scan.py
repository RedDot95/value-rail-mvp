"""Scan pipeline.

Per route candidate: fetch everything from the connector FIRST (no DB transaction open), then
persist snapshots + quotes + evidence + RouteEvaluation + alert outbox row in ONE transaction.
A failing source marks the scan `degraded` and the source `down` - never "no deals".
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..alerts.outbox import enqueue_if_needed
from ..connectors.base import CapabilityNotSupported, Connector, DiscoveryItem, QuoteBundle, SourceUnavailable
from ..domain.enums import ScanStatus
from ..evidence import content_hash
from ..settings import Settings
from ..storage.orm import OperatorProfileRow, RouteEvaluationRow, ScanRunRow, SourceRow
from ..storage.repo import (active_rule_version, ensure_rule_version, get_or_create_product, insert_evidence,
                            insert_offer_snapshot, insert_quote, mark_source_health, rule_params_of, upsert_source)
from ..valuation.engine import ENGINE_VERSION, evaluate_route
from ..valuation.models import EvaluationResult, OfferInput, RouteInputs, RuleParams
from .exit_rules import exit_quote_from_rule
from .sellers import track_seller_offers

log = logging.getLogger("value_rail.worker")


class ScanReport(BaseModel):
    scan_run_id: int
    status: ScanStatus
    items_seen: int = 0
    evaluations_created: int = 0
    alerts_enqueued: int = 0
    sources_failed: dict[str, str] = Field(default_factory=dict)
    statuses: dict[str, str] = Field(default_factory=dict)
    evaluation_ids: dict[str, int] = Field(default_factory=dict)
    offers_seen: int = 0
    seller_events: dict[str, int] = Field(default_factory=dict)
    items_out_of_scope: int = 0


class _Fetched(BaseModel):
    item: DiscoveryItem
    offers: list[Any]
    checkout: QuoteBundle | None
    exit: QuoteBundle | None


def _fetch(connector: Connector, item: DiscoveryItem, now: datetime) -> _Fetched:
    raws = connector.offer_fetch(item, now)
    offers = [connector.normalize(item, r, now) for r in raws]
    caps = connector.capabilities()
    checkout = exit_ = None
    try:
        checkout = connector.checkout_quote(item, now) if caps.checkout_quote else None
    except CapabilityNotSupported:
        checkout = None
    try:
        exit_ = connector.exit_quote(item, now) if caps.exit_quote else None
    except CapabilityNotSupported:
        exit_ = None
    return _Fetched(item=item, offers=offers, checkout=checkout, exit=exit_)


def persist_evaluation(s: Session, *, inputs: RouteInputs, result: EvaluationResult, rule_version_id: int,
                       scan_run_id: int | None, operator_profile_id: int | None, product_id: int | None) -> RouteEvaluationRow:
    inputs_json = inputs.model_dump(mode="json")
    row = RouteEvaluationRow(
        route_key=inputs.route_key, scan_run_id=scan_run_id, rule_version_id=rule_version_id,
        operator_profile_id=operator_profile_id, product_id=product_id, evaluated_at=inputs.evaluated_at,
        status=str(result.status), discount=result.discount, profit_eur=result.profit_eur, edge=result.edge,
        evaluated_quantity=str(result.evaluated_quantity), inputs=inputs_json, outputs=result.canonical(),
        inputs_hash=content_hash(inputs_json), engine_version=ENGINE_VERSION, is_synthetic=inputs.is_synthetic)
    s.add(row)
    s.flush()
    return row


def _operator(s: Session, name: str | None, *, synthetic: bool) -> OperatorProfileRow | None:
    q = select(OperatorProfileRow).where(OperatorProfileRow.is_synthetic == synthetic)
    if name:
        q = q.where(OperatorProfileRow.name == name)
    return s.scalar(q.order_by(OperatorProfileRow.id).limit(1))


def _persist_item(s: Session, f: _Fetched, *, scan_id: int | None, rv_id: int, params: RuleParams,
                  operator: OperatorProfileRow | None, settings: Settings, now: datetime) -> tuple[RouteEvaluationRow, EvaluationResult, bool]:
    item = f.item
    exit_bundle, exit_rule = f.exit, None
    if exit_bundle is None:
        exit_bundle, exit_rule = exit_quote_from_rule(params, item, now)
    specs = list(item.sources) + ([exit_bundle.source] if exit_rule is not None else [])
    srcs: dict[str, SourceRow] = {}
    for spec in specs:
        srcs[spec.key] = upsert_source(s, key=spec.key, name=spec.name, kind=str(spec.kind), role=str(spec.role),
                                       is_synthetic=item.is_synthetic)
    product = get_or_create_product(s, item.product, family=item.product_family, now=now, is_synthetic=item.is_synthetic)

    offer_inputs: list[OfferInput] = []
    for o in f.offers:
        src = srcs[o.source.key]
        row = insert_offer_snapshot(
            s, source=src, product=product, scan_run_id=scan_id, route_key=item.route_key, captured_at=o.captured_at,
            price_amount=o.unit_price, price_currency=o.currency, price_text_raw=o.price_text_raw,
            price_includes_fees=o.price_includes_fees, fees=[x.model_dump(mode="json") for x in o.fees],
            advertised=o.advertised_quantity, checkout_confirmed=o.checkout_confirmed_quantity,
            purchased=o.purchased_quantity, raw=o.raw | {"identity": o.identity.model_dump(mode="json")},
            is_synthetic=o.is_synthetic)
        ref = f"offer_snapshot:{row.id}"
        ev_refs = [f"evidence:{insert_evidence(s, d, subject_ref=ref, source=src).id}" for d in o.evidence]
        offer_inputs.append(OfferInput(
            offer_ref=ref, source_key=src.key, source_role=o.source.role, identity=o.identity, unit_price=o.unit_price,
            currency=o.currency, price_includes_fees=o.price_includes_fees, fees=o.fees,
            advertised_quantity=o.advertised_quantity, checkout_confirmed_quantity=o.checkout_confirmed_quantity,
            purchased_quantity=o.purchased_quantity, captured_at=o.captured_at, evidence_refs=ev_refs))

    def _store_quote(b: QuoteBundle | None, kind: str):
        if b is None:
            return None
        q = b.quote
        src = srcs[b.source.key]
        row = insert_quote(
            s, kind=kind, source=src, product=product, scan_run_id=scan_id, route_key=item.route_key,
            identity=q.identity.model_dump(mode="json"),
            quantity=getattr(q, "quantity_confirmed", "unknown"), unit_price=q.unit_price, currency=q.currency,
            depth_quantity=getattr(q, "depth_quantity", "unknown"), fees=[x.model_dump(mode="json") for x in q.fees],
            captured_at=q.captured_at, valid_until=q.valid_until, is_synthetic=item.is_synthetic)
        ref = f"quote:{row.id}"
        ev_refs = [f"evidence:{insert_evidence(s, d, subject_ref=ref, source=src).id}" for d in b.evidence]
        return q.model_copy(update={"quote_ref": ref, "evidence_refs": ev_refs})

    checkout = _store_quote(f.checkout, "checkout")
    exit_q = _store_quote(exit_bundle, "exit")

    caps = dict(operator.capabilities) if operator else {}
    prereq_names = list(dict.fromkeys(list(item.prerequisites) + (list(exit_rule.prerequisites) if exit_rule else [])))
    proofs = caps.get("_evidence", {})
    connector_prereqs = [{"name": n, "status": ("unknown" if not item.is_synthetic
                         and caps.get(n) == "proven" and proofs.get(n, "unknown") in ("", "unknown")
                         else caps.get(n, "unknown")),
                         "evidence_ref": proofs.get(n, "unknown")} for n in prereq_names]
    inputs = RouteInputs(route_key=item.route_key, product=item.product, offers=offer_inputs, checkout_quote=checkout,
                         exit_quote=exit_q, prerequisites=connector_prereqs, evaluated_at=now,
                         is_synthetic=item.is_synthetic)
    result = evaluate_route(inputs, params)
    ev_row = persist_evaluation(s, inputs=inputs, result=result, rule_version_id=rv_id, scan_run_id=scan_id,
                                operator_profile_id=operator.id if operator else None, product_id=product.id)
    decision, alert = enqueue_if_needed(s, ev_row, result, settings.file_config.alerts, now)
    log.info("evaluated %s -> %s (alert: %s)", item.route_key, result.status, decision.reason)
    return ev_row, result, alert is not None


def _enrich_after_scan(session_factory: sessionmaker[Session], enricher: Any, jobs: list[tuple[Any, ...]],
                       scan_id: int) -> None:
    """Optional INFERRED enrichment (D-42), strictly after all deterministic evaluations are committed.

    Purely additive: writes only `offer_judgments`; never touches evaluations, alerts or the ScanReport.
    Any failure is logged and swallowed.
    """
    try:
        from ..judgments.service import context_from_offer
        max_chars = enricher.cfg.max_state_chars
        contexts = []
        for item, offers, ev_id, refs in jobs:
            for o, ref in zip(offers, refs):
                snap_id = int(ref.split(":", 1)[1]) if ref.startswith("offer_snapshot:") else None
                contexts.append(context_from_offer(item, o, max_chars=max_chars, offer_snapshot_id=snap_id,
                                                   route_evaluation_id=ev_id, scan_run_id=scan_id))
        enricher.begin_run()
        er, _ = enricher.run(contexts, session_factory=session_factory)
        log.info("enrichment (%s, inferred only): %d offers, %d requests, %d judgments, %d advisory blocks, "
                 "%d suspected block pages, %d skipped (budget)", er.provider, er.offers_seen, er.requests,
                 er.judgments_persisted, er.advisory_blocks, er.suspected_block_pages, er.skipped_budget)
    except Exception as exc:  # noqa: BLE001 - enrichment must never break or alter a scan
        log.warning("enrichment skipped after scan #%s: %s", scan_id, type(exc).__name__)


def run_scan(session_factory: sessionmaker[Session], connector: Connector, settings: Settings, now: datetime, *,
             trigger: str = "cli", operator_name: str | None = None, enricher: Any = None, guard=None) -> ScanReport:
    """`enricher`: optional judgments.EnrichmentService (tests inject one). When None, one is built only if
    [enrichment].enabled is true; otherwise nothing enrichment-related is imported or constructed."""
    def check(s=None):
        if guard is not None:
            guard(s)

    check()
    if enricher is None and settings.file_config.enrichment.enabled:
        from ..judgments.service import build_enrichment_service
        enricher = build_enrichment_service(settings)
    enrich_jobs: list[tuple[Any, ...]] = []
    caps = connector.capabilities()
    with session_factory.begin() as s:
        check(s)
        # Register declared single-source connectors even if discovery yields no
        # offers or fails before producing a route candidate.
        spec = getattr(connector, "source", None)
        if spec is not None:
            upsert_source(s, key=spec.key, name=spec.name, kind=str(spec.kind), role=str(spec.role),
                          is_synthetic=caps.synthetic)
        rv = active_rule_version(s, now)
        if rv is None:
            rv = ensure_rule_version(s, RuleParams.model_validate(settings.file_config.rules.model_dump()), now=now)
        rv_id, params = rv.id, rule_params_of(rv)
        scan = ScanRunRow(started_at=now, status=ScanStatus.RUNNING.value, trigger=trigger, sources_ok=[],
                          sources_failed={}, is_synthetic=caps.synthetic,
                          notes="OFFLINE fixture scan (SYNTHETIC)" if caps.synthetic else
                          (f"LIVE scan {connector.key}" if caps.live_network else ""))
        s.add(scan)
        s.flush()
        scan_id = scan.id
        configured_operator = settings.file_config.operator
        selected_name = operator_name or (configured_operator.name if configured_operator and not caps.synthetic else None)
        op = (_operator(s, selected_name, synthetic=caps.synthetic)
              if caps.synthetic or selected_name else None)
        op_id = op.id if op else None

    rep = ScanReport(scan_run_id=scan_id, status=ScanStatus.RUNNING)
    ok_sources: set[str] = set()
    seller_offers: list[dict[str, Any]] = []
    try:
        check()
        items = connector.discovery(now)
        check()
    except SourceUnavailable as exc:
        items = []
        rep.sources_failed[exc.source_key] = str(exc)
    for item in items:
        check()
        rep.items_seen += 1
        from ..catalog import in_scope
        if not in_scope(item, settings):
            rep.items_out_of_scope += 1
            continue
        try:
            fetched = _fetch(connector, item, now)
            check()
        except SourceUnavailable as exc:
            rep.sources_failed[exc.source_key] = str(exc)
            with session_factory.begin() as s:
                check(s)
                spec = next((x for x in item.sources if x.key == exc.source_key), None)
                if spec is not None:
                    src = upsert_source(s, key=spec.key, name=spec.name, kind=str(spec.kind), role=str(spec.role),
                                        is_synthetic=item.is_synthetic)
                    mark_source_health(s, src, ok=False, now=now, error=str(exc))
            log.warning("source unavailable during %s: %s (route NOT evaluated; disturbance)", item.route_key, exc)
            continue
        with session_factory.begin() as s:
            check(s)
            operator = s.get(OperatorProfileRow, op_id) if op_id else None
            ev_row, result, alerted = _persist_item(s, fetched, scan_id=scan_id, rv_id=rv_id, params=params,
                                                    operator=operator, settings=settings, now=now)
        rep.evaluations_created += 1
        rep.offers_seen += len(fetched.offers)
        seller_offers.extend(o.raw["seller_offer"] for o in fetched.offers if isinstance(o.raw.get("seller_offer"), dict))
        rep.alerts_enqueued += int(alerted)
        rep.statuses[item.route_key] = str(result.status)
        rep.evaluation_ids[item.route_key] = ev_row.id
        ok_sources.update(x.key for x in item.sources if x.key not in rep.sources_failed)
        if enricher is not None:
            enrich_jobs.append((item, fetched.offers, ev_row.id, [o["offer_ref"] for o in ev_row.inputs["offers"]]))

    if rep.sources_failed:
        rep.status = ScanStatus.DEGRADED if rep.evaluations_created else ScanStatus.FAILED
    else:
        rep.status = ScanStatus.OK
    ok_pages = set(getattr(connector, "ok_pages", set()) or set())
    spec = getattr(connector, "source", None)
    if ok_pages and spec is not None:
        ok_sources.add(spec.key)  # a proven empty page is a successful observation
    if seller_offers or ok_pages:
        with session_factory.begin() as s:
            check(s)
            # Filtered products are not disappearance evidence for previously tracked offers.
            gone_pages = set() if rep.items_out_of_scope else ok_pages
            rep.seller_events = track_seller_offers(s, seller_offers, gone_pages, now=now, scan_run_id=scan_id)
    with session_factory.begin() as s:
        check(s)
        # A later successful item must not erase a failure from the same source.
        # This also records discovery failures for already registered sources.
        for key in ok_sources | set(rep.sources_failed):
            src = s.scalar(select(SourceRow).where(SourceRow.key == key))
            if src is not None and not key.startswith("rule-exit:"):
                mark_source_health(s, src, ok=key not in rep.sources_failed, now=now,
                                   error=rep.sources_failed.get(key))
        scan = s.get(ScanRunRow, scan_id)
        scan.finished_at = now
        scan.status = rep.status.value
        scan.sources_ok = sorted(ok_sources - set(rep.sources_failed))
        scan.sources_failed = rep.sources_failed
        scan.items_seen = rep.items_seen
        scan.evaluations_created = rep.evaluations_created
        scan.alerts_enqueued = rep.alerts_enqueued
        if rep.items_out_of_scope:
            scan.notes += f"; {rep.items_out_of_scope} candidates outside liquid-value scope (not evaluated)"
    if enricher is not None and enrich_jobs:
        _enrich_after_scan(session_factory, enricher, enrich_jobs, scan_id)
    return rep
