"""View-model assembly for templates (keeps templates logic-free)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.enums import STATUS_LABEL_DE, RouteStatus
from ..settings import Settings
from ..storage.orm import AlertRow, RouteEvaluationRow, RuleVersionRow, SourceRow, SellerOfferRow
from ..storage.repo import evidence_for_refs, judgments_for_offer_refs, latest_evaluations, latest_scan_runs


def _source_keys(ev: RouteEvaluationRow) -> set[str]:
    inp = ev.inputs or {}
    keys = {o.get("source_key") for o in inp.get("offers", [])}
    if inp.get("checkout_quote"):
        keys.add(inp["checkout_quote"].get("source_key"))
    if inp.get("exit_quote"):
        keys.add(inp["exit_quote"].get("venue_key"))
    return {k for k in keys if k}


def card(ev: RouteEvaluationRow, *, sources_down: set[str], now: datetime, stale_after: int) -> dict[str, Any]:
    o = ev.outputs
    age = (now - ev.evaluated_at).total_seconds()
    down = sorted(_source_keys(ev) & sources_down)
    stale_reasons = []
    if age > stale_after:
        stale_reasons.append(f"Bewertung {int(age // 60)} min alt")
    if down:
        stale_reasons.append("Quelle gestört: " + ", ".join(down))
    return {
        "id": ev.id, "route_key": ev.route_key, "status": ev.status,
        "status_de": "Arbitrage-Kandidat" if o.get("screening") and ev.status == "price_find" else STATUS_LABEL_DE[RouteStatus(ev.status)], "outputs": o, "evaluated_at": ev.evaluated_at,
        "synthetic": ev.is_synthetic, "stale": bool(stale_reasons), "stale_reasons": stale_reasons,
        "title": o.get("screening", {}).get("title", ev.route_key.removeprefix("synthetic:")),
    }


def monitored_evaluations(s: Session, settings: Settings):
    allowed = settings.file_config.scope.allowed_source_keys
    clearance_only = any(c.enabled and c.kind == "coingate_clearance" for c in settings.file_config.connectors)
    active = set(s.scalars(select(SellerOfferRow.offer_key).where(SellerOfferRow.source_key == "coingate", SellerOfferRow.active.is_(True)))) if clearance_only else set()
    return [ev for ev in latest_evaluations(s)
            if (not allowed or bool(_source_keys(ev) & set(allowed)))
            and (not clearance_only or ev.route_key in active)]


def dashboard(s: Session, settings: Settings, now: datetime) -> dict[str, Any]:
    stale_after = settings.file_config.scan_intervals.stale_after_seconds
    sources = list(s.scalars(select(SourceRow).order_by(SourceRow.key)))
    down = {x.key for x in sources if x.health == "down"}
    evaluations = monitored_evaluations(s, settings)
    cards = [card(e, sources_down=down, now=now, stale_after=stale_after) for e in evaluations]
    groups: dict[str, list] = {k: [] for k in ("price_find", "verified_route", "expired", "blocked", "no_signal")}
    for c in cards:
        groups.setdefault(c["status"], []).append(c)
    return {"groups": groups, "screener_mode": settings.file_config.rules.evaluation_mode == "screener", "system": system_status(s, settings, now), "any_synthetic": any(c["synthetic"] for c in cards)}


def system_status(s: Session, settings: Settings, now: datetime) -> dict[str, Any]:
    sources = list(s.scalars(select(SourceRow).order_by(SourceRow.key)))
    allowed = settings.file_config.scope.allowed_source_keys
    if allowed:
        sources = [x for x in sources if x.key in allowed]
    scans = latest_scan_runs(s, 10)
    outbox = dict(s.execute(select(AlertRow.state, func.count()).group_by(AlertRow.state)).all())
    last = scans[0] if scans else None
    if last is None:
        headline, level = "Noch kein Scan gelaufen", "warn"
    elif last.status == "ok":
        headline, level = "Letzter Scan ok", "ok"
    else:
        headline, level = ("Störung: " + ", ".join(sorted(last.sources_failed)) +
                           " – keine Aussage über Angebote dieser Quelle (Störung ≠ keine Deals)"), "bad"
    stale_after = settings.file_config.scan_intervals.stale_after_seconds
    last_age = (now - last.finished_at).total_seconds() if last and last.finished_at else None
    if last_age is not None and last_age > stale_after:
        headline += f" – Daten veraltet ({int(last_age // 60)} min)"
        level = "bad" if level == "bad" else "warn"
    rule = s.scalar(select(RuleVersionRow).order_by(RuleVersionRow.valid_from.desc(), RuleVersionRow.id.desc()).limit(1))
    return {"headline": headline, "level": level, "sources": sources, "scans": scans, "outbox": outbox,
            "rule": rule, "intervals": settings.file_config.scan_intervals, "live_scanning": False,
            "auth_enabled": settings.auth_enabled}


def evaluation_detail(s: Session, ev_id: int, settings: Settings, now: datetime) -> dict[str, Any] | None:
    ev = s.get(RouteEvaluationRow, ev_id)
    if ev is None:
        return None
    sources = list(s.scalars(select(SourceRow)))
    down = {x.key for x in sources if x.health == "down"}
    c = card(ev, sources_down=down, now=now, stale_after=settings.file_config.scan_intervals.stale_after_seconds)
    inp = ev.inputs
    refs: list[str] = []
    for o in inp.get("offers", []):
        refs.append(o["offer_ref"])
    for k in ("checkout_quote", "exit_quote"):
        if inp.get(k):
            refs.append(inp[k]["quote_ref"])
    evidence = evidence_for_refs(s, refs)
    rule = s.get(RuleVersionRow, ev.rule_version_id)
    alerts = list(s.scalars(select(AlertRow).where(AlertRow.route_key == ev.route_key).order_by(AlertRow.id.desc()).limit(5)))
    vm = {"card": c, "ev": ev, "inputs": inp, "evidence": evidence, "rule": rule, "alerts": alerts}
    enr = settings.file_config.enrichment
    if enr.enabled and enr.show_in_ui:  # INFERRED (model) signals, shown separately from observed values (D-42)
        from ..judgments.safety import advisory_view
        offer_refs = [o["offer_ref"] for o in inp.get("offers", [])]
        rows = [j for j in judgments_for_offer_refs(s, offer_refs) if j.route_evaluation_id in (None, ev.id)]
        vm["inferred"] = {"rows": rows, "view": advisory_view(ev.status, [j.signal for j in rows])}
    return vm
