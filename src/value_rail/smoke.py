"""Live smoke test for one real connector (explicit operator action, never part of the default test run).

Runs ONE real scan through the normal pipeline (robots.txt, SSRF guard, politeness, evaluation, evidence)
and writes a dated Markdown report. A blocked, failed or unprofitable result is a correct outcome.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from .connectors.registry import build_one, connector_config
from .domain.enums import STATUS_LABEL_DE, RouteStatus
from .domain.timeutil import DISPLAY_TZ, utcnow
from .services import AppContext
from .storage.orm import EvidenceRow, OfferSnapshotRow, RouteEvaluationRow
from .worker.scan import ScanReport, run_scan


def _berlin(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    return dt.astimezone(DISPLAY_TZ).strftime(fmt)


def run_smoke(ctx: AppContext, key: str, *, out_dir: Path | None, now: datetime | None = None,
              connector=None) -> tuple[ScanReport, str]:
    cfg = connector_config(ctx.settings, key)
    if cfg is None:
        raise KeyError(f"no [[connectors]] entry with key {key!r}")
    conn = connector or build_one(ctx.settings, cfg)
    caps = conn.capabilities()
    started = now or utcnow()
    t0 = time.monotonic()
    rep = run_scan(ctx.session_factory, conn, ctx.settings, started, trigger=f"smoke:{key}")
    elapsed = time.monotonic() - t0
    finished = utcnow() if now is None else started
    client = getattr(conn, "client", None)
    req_log = list(getattr(client, "request_log", []))

    lines = [f"# Live smoke test `{key}` - {_berlin(started, '%Y-%m-%d')}", "",
             f"- Start: {_berlin(started)} (UTC {started.strftime('%H:%M:%S')})",
             f"- Ende: {_berlin(finished)} (Dauer {elapsed:.1f} s)",
             f"- Connector: `{key}` (kind `{cfg.kind}`), live_network={caps.live_network}, "
             f"checkout_quote={caps.checkout_quote}, exit_quote={caps.exit_quote}",
             f"- Capability-Notiz: {caps.notes}",
             f"- Scan-Run #{rep.scan_run_id}: **{rep.status.value}** - {rep.items_seen} Kandidaten, "
             f"{rep.evaluations_created} Bewertungen, {rep.alerts_enqueued} Alerts",
             f"- Gestoerte Quellen: {rep.sources_failed or 'keine'}", "", "## HTTP-Requests", ""]
    if req_log:
        lines += ["| # | URL | Status |", "|---|---|---|"]
        lines += [f"| {i} | {u} | {st} |" for i, (u, st) in enumerate(req_log, 1)]
    else:
        lines.append("(keine)")
    lines += ["", "## Bewertungen", ""]
    n_offers = 0
    price_finds = 0
    with ctx.session_factory() as s:
        if rep.evaluation_ids:
            lines += ["| Route | Status | Preis | Nennwert | Blockgruende | fehlende Nachweise |", "|---|---|---|---|---|---|"]
        for route_key, ev_id in rep.evaluation_ids.items():
            ev = s.get(RouteEvaluationRow, ev_id)
            o = ev.outputs
            offers = s.scalars(select(OfferSnapshotRow).where(OfferSnapshotRow.scan_run_id == rep.scan_run_id,
                                                              OfferSnapshotRow.route_key == route_key)).all()
            n_offers += len(offers)
            price = ", ".join(f"{x.price_amount} {x.price_currency}" for x in offers) or "-"
            st = RouteStatus(ev.status)
            price_finds += int(st == RouteStatus.PRICE_FIND)
            lines.append(f"| {route_key} | {STATUS_LABEL_DE[st]} | {price} | {o.get('face_value_reference_eur')} | "
                         f"{', '.join(o.get('block_reasons', [])) or '-'} | {', '.join(o.get('missing_evidence', [])) or '-'} |")
        ev_count = s.scalar(select(EvidenceRow.id).order_by(EvidenceRow.id.desc()).limit(1))
    lines += ["", f"- Angebote (Offer-Snapshots) gespeichert: **{n_offers}**",
              f"- Preisfunde: **{price_finds}**, verifizierte Routen: "
              f"**{sum(1 for v in rep.statuses.values() if v == 'verified_route')}**",
              f"- Seller-Offer-Events: {rep.seller_events or 'keine'}",
              f"- Letzte Evidence-ID: {ev_count}", "",
              "Ein blockiertes oder unprofitables Ergebnis ist ein korrektes Ergebnis. Es wurde nichts gekauft, "
              "kein Checkout/Warenkorb/Konto aufgerufen und keine Sperre umgangen.", ""]
    md = "\n".join(lines)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"live_smoke_{_berlin(started, '%Y-%m-%d')}_{key}.md"
        path.write_text(md, encoding="utf-8")
    return rep, md
