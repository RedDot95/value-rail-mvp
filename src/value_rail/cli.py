"""CLI for dev / replay / diagnose. Entry point: `value-rail` (or `python -m value_rail.cli`)."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Optional

import typer
from sqlalchemy import func, select

from .alerts.dispatcher import dispatch_pending
from .alerts.eligibility import delivery_check
from .alerts.sinks import build_sink_from_settings
from .connectors.registry import describe_connectors
from .domain.enums import STATUS_LABEL_DE, RouteStatus
from .domain.money import fmt_eur, fmt_pct
from .domain.timeutil import to_display, utcnow
from .logging_setup import configure_logging
from .services import AppContext
from .storage.orm import AlertRow, OfferJudgmentRow, RouteEvaluationRow, RuleVersionRow, ScanRunRow, SourceRow
from .storage.repo import active_rule_version, add_rule_version, latest_evaluations, rule_params_of
from .valuation.replay import replay_evaluation
from .worker.scheduler import run_cycle, run_forever

app = typer.Typer(help="Value Rail - liquid-value route research, evidence and coverage; never purchases",
                  no_args_is_help=True)
rules_app = typer.Typer(help="Versioned valuation rules")
app.add_typer(rules_app, name="rules")


@app.command("import-quotes")
def import_quotes_command(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Import real operator-reviewed quotes and hash-bound artifacts; never sends or buys."""
    from .quote_import import import_quotes
    from pydantic import ValidationError
    ctx = _ctx()
    try:
        report = import_quotes(ctx, path, utcnow())
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_url=False)
        typer.echo(json.dumps({"rejected": errors}, default=str), err=True)
        raise typer.Exit(2) from None
    except (ValueError, OSError) as exc:
        typer.echo(f"Quote import rejected: {exc}", err=True)
        raise typer.Exit(2) from None
    typer.echo(json.dumps(report, ensure_ascii=False))


@app.command("quote-template")
def quote_template(evaluation_id: int = typer.Argument(...)) -> None:
    """Print an incomplete quote manifest with the stored product identity; never invent values."""
    ctx = _ctx()
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow, evaluation_id)
        if ev is None or ev.is_synthetic:
            typer.echo("A real evaluation is required", err=True)
            raise typer.Exit(2)
        quote = {"identity": ev.inputs["product"], "source_url": "", "source_name": "", "unit_price": "unknown",
                 "currency": "EUR", "quantity": "unknown", "captured_at": None, "valid_until": None,
                 "firm": False, "fees_complete": False, "fees": [], "artifact": "", "artifact_sha256": ""}
        cfg = ctx.settings.file_config.operator
        document = {"schema_version": 1, "evaluation_id": ev.id,
                    "reviewed_by": cfg.name if cfg else "", "checkout": quote, "exit": quote.copy()}
    typer.echo(json.dumps(document, indent=2, ensure_ascii=False))


def _ctx(init: bool = True) -> AppContext:
    ctx = AppContext()
    configure_logging(ctx.settings.log_level)
    if init:
        ctx.init_db()
    return ctx


@app.command("init-db")
def init_db() -> None:
    """Apply Alembic migrations and seed rule version + SYNTHETIC operator profile."""
    ctx = _ctx()
    typer.echo(f"DB ready: {ctx.settings.database_url}")


@app.command("load-fixtures")
def load_fixtures(down: list[str] = typer.Option([], "--down", help="Simulate an outage of this source key"),
                  no_dispatch: bool = typer.Option(False, "--no-dispatch", help="Leave alerts pending in the outbox")) -> None:
    """Run one OFFLINE scan over the SYNTHETIC fixtures and dispatch log alerts."""
    ctx = _ctx()
    for r in run_cycle(ctx, down_sources=set(down), dispatch=not no_dispatch, trigger="cli"):
        typer.echo(f"scan #{r.scan_run_id}: {r.status} · {r.evaluations_created} Bewertungen · "
                   f"{r.alerts_enqueued} neue Alerts · gestoert: {r.sources_failed or '-'}")
        for k, st in r.statuses.items():
            typer.echo(f"  {STATUS_LABEL_DE[RouteStatus(st)]:<20} {k}")


app.command("scan", help="Alias of load-fixtures: scans all ENABLED connectors (default: offline fixtures only).")(load_fixtures)


@app.command()
def smoke(connector: str = typer.Argument(..., help="connector key, e.g. 'coingate'"),
          out_dir: str = typer.Option("docs", "--out-dir", help="where live_smoke_<date>_<key>.md is written ('' = none)")) -> None:
    """LIVE smoke test of one real connector (network!). Writes docs/live_smoke_<Berlin date>_<key>.md."""
    from pathlib import Path

    from .smoke import run_smoke
    ctx = _ctx()
    rep, md = run_smoke(ctx, connector, out_dir=Path(out_dir) if out_dir else None)
    typer.echo(md)
    raise typer.Exit(code=0 if rep.status.value in ("ok", "degraded") else 2)


@app.command()
def dispatch() -> None:
    """Send pending outbox alerts via the configured sink (log)."""
    ctx = _ctx()
    cfg = ctx.settings.file_config.alerts
    rep = dispatch_pending(ctx.session_factory, build_sink_from_settings(ctx.settings), utcnow(),
                           backoff_seconds=cfg.retry_backoff_seconds, eligibility=delivery_check(ctx.settings))
    typer.echo(rep.model_dump_json())


@app.command()
def replay(evaluation_id: int) -> None:
    """Recompute a stored evaluation with its stored rule version and inputs."""
    ctx = _ctx()
    with ctx.session_factory() as s:
        res = replay_evaluation(s, evaluation_id)
    typer.echo(json.dumps(res.model_dump(mode="json"), indent=2))
    raise typer.Exit(0 if res.match else 1)


@app.command("evaluations")
def list_evaluations() -> None:
    """Latest evaluation per route."""
    ctx = _ctx()
    with ctx.session_factory() as s:
        for e in latest_evaluations(s):
            o = e.outputs
            typer.echo(f"#{e.id:<4} {STATUS_LABEL_DE[RouteStatus(e.status)]:<20} {e.route_key:<45} "
                       f"Rabatt {fmt_pct(o['discount']):>10}  Profit {fmt_eur(o['profit_eur']):>12}  Edge {fmt_pct(o['edge']):>10}"
                       f"{'  [SYNTHETIC]' if e.is_synthetic else ''}")


@app.command()
def diagnose() -> None:
    """Print configuration, DB state, connectors and capabilities."""
    ctx = _ctx()
    st = ctx.settings
    with ctx.session_factory() as s:
        info = {
            "database_url": st.database_url,
            "config_path": str(st.config_path),
            "fixtures_dir": str(st.fixtures_dir),
            "auth_enabled": st.auth_enabled,
            "live_scanning": any(c.enabled and c.kind not in ("fixture", "placeholder", "blocked")
                                 for c in st.file_config.connectors),
            "rule_version": (lambda r: {"id": r.id, "label": r.label, "params": r.params} if r else None)(active_rule_version(s, utcnow())),
            "counts": {t.__tablename__: s.scalar(select(func.count()).select_from(t)) for t in
                       (SourceRow, ScanRunRow, RouteEvaluationRow, AlertRow, RuleVersionRow)},
            "outbox": dict(s.execute(select(AlertRow.state, func.count()).group_by(AlertRow.state)).all()),
            "sources": [{"key": x.key, "health": x.health, "last_error": x.last_error} for x in s.scalars(select(SourceRow))],
            "last_scan": (lambda r: {"id": r.id, "status": r.status, "at": to_display(r.started_at),
                                     "failed": r.sources_failed} if r else None)(
                s.scalar(select(ScanRunRow).order_by(ScanRunRow.id.desc()).limit(1))),
            "connectors": describe_connectors(st),
            "enrichment": {"enabled": st.file_config.enrichment.enabled,
                           "provider_configured": st.file_config.enrichment.provider,
                           "provider_effective": st.enrichment_provider_effective,
                           "typesafe_api_key_present": st.typesafe_configured,  # never the key itself
                           "model": st.file_config.enrichment.model,
                           "judgments_stored": s.scalar(select(func.count()).select_from(OfferJudgmentRow))},
            "scan_intervals": st.file_config.scan_intervals.model_dump(),
        }
    typer.echo(json.dumps(info, indent=2, default=str, ensure_ascii=False))


@app.command()
def coverage(json_output: bool = typer.Option(False, "--json", help="Machine-readable catalogue, scope and actual evidence gaps")):
    """Show liquid-value candidates, real monitoring coverage and why routes lack proof."""
    from .coverage import coverage_report

    ctx = _ctx()
    with ctx.session_factory() as s:
        report = coverage_report(s, ctx.settings, utcnow())
    if json_output:
        typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
        return
    if report["screener_mode"]:
        typer.echo(f"{report['candidate_count']} Instrumente; {report['explicitly_targeted_count']} gezielt angebunden; {len(report['candidate_signals_now'])} aktuelle Arbitrage-Kandidaten")
        typer.echo(report["note"])
        return
    typer.echo(f"{report['candidate_count']} candidates; {report['explicitly_targeted_count']} explicitly targeted; "
               f"{len(report['verified_routes_now'])} fresh verified profitable routes")
    typer.echo(f"Verified-only alerts: {report['verified_only_alerts']}; real operator: {report['real_operator_configured']}")
    for item in report["instruments"]:
        sources = ", ".join(item["targeted_sources"]) or "no explicit target"
        typer.echo(f"{item['label']}: {sources}; observations={item['observations']}; exit proof=unproven")
    typer.echo(report["note"])


@app.command()
def enrich(dry_run: bool = typer.Option(False, "--dry-run",
                                        help="OFFLINE: enrich the SYNTHETIC fixture offers in memory, write nothing"),
           block_page_sample: bool = typer.Option(True, "--block-page-sample/--no-block-page-sample",
                                                  help="dry-run: also assess a SYNTHETIC block-page payload"),
           limit: int = typer.Option(0, "--limit", help="max offers (0 = all, still bounded by the request budget)")) -> None:
    """Model-judgment ENRICHMENT (inferred hints only; never valuation math, never alerts, never purchases).

    --dry-run uses the configured provider (null by default -> explicit abstain) against the fixture offers.
    Without --dry-run: requires [enrichment].enabled; enriches the offers of the latest evaluations and stores
    them in offer_judgments.
    """
    from .connectors.fixture import FixtureConnector
    from .judgments.questions import SELECT_FACE_VALUE
    from .judgments.safety import advisory_view
    from .judgments.service import (EnrichmentService, OfferContext, build_provider, context_from_offer,
                                    context_from_snapshot)
    ctx = _ctx(init=not dry_run)
    st = ctx.settings
    cfg = st.file_config.enrichment
    if not dry_run and not cfg.enabled:
        typer.echo("[enrichment].enabled = false -> nothing to do (use --dry-run for the offline path)", err=True)
        raise typer.Exit(2)
    svc = EnrichmentService(build_provider(st), cfg)
    now = utcnow()
    contexts: list[OfferContext] = []
    statuses: dict[str, str] = {}
    if dry_run:
        conn = FixtureConnector(Path(st.fixtures_dir))
        for item in conn.discovery(now):
            for raw in conn.offer_fetch(item, now):
                contexts.append(context_from_offer(item, conn.normalize(item, raw, now), max_chars=cfg.max_state_chars))
        sample = Path(st.fixtures_dir) / "enrichment" / "synthetic_block_page.html"
        if block_page_sample and sample.exists():
            contexts.append(OfferContext(route_key="synthetic:block-page-sample", source_key="synthetic-block-sample",
                                         source_name="SYNTHETIC block page sample", title="(fetched page)",
                                         payload=sample.read_text(encoding="utf-8")[: cfg.max_state_chars],
                                         is_synthetic=True))
    else:
        from .storage.orm import OfferSnapshotRow, ProductRow, SourceRow
        with ctx.session_factory() as s:
            for ev in latest_evaluations(s):
                statuses[ev.route_key] = ev.status
                for o in (ev.inputs or {}).get("offers", []):
                    ref = o.get("offer_ref", "")
                    if not ref.startswith("offer_snapshot:"):
                        continue
                    snap = s.get(OfferSnapshotRow, int(ref.split(":", 1)[1]))
                    if snap is None:
                        continue
                    contexts.append(context_from_snapshot(snap, s.get(ProductRow, snap.product_id),
                                                          s.get(SourceRow, snap.source_id), route_evaluation_id=ev.id,
                                                          max_chars=cfg.max_state_chars))
    if limit:
        contexts = contexts[:limit]
    rep, outcomes = svc.run(contexts, session_factory=None if dry_run else ctx.session_factory)
    typer.echo(f"enrichment {'DRY-RUN (nothing stored)' if dry_run else 'stored'} · provider={svc.provider_name} · "
               f"enabled={cfg.enabled} · INFERRED (model) hints only - observed values and valuation unchanged")
    for out in outcomes:
        c = out.context
        typer.echo(f"- {c.route_key}  [{c.source_key}]{'  SYNTHETIC' if c.is_synthetic else ''}")
        for r in out.results:
            val = "abstain" if r.abstained else f"{r.answer} p={r.probability if r.probability is not None else '-'}" \
                  f"{'' if r.confidence is None else f' conf={r.confidence}'}"
            typer.echo(f"    {r.question_id:<22} {val:<40} signal={out.signals.get(r.question_id)}"
                       f"{'  (' + r.abstain_reason + ')' if r.abstained and r.abstain_reason else ''}")
            if r.question_id == SELECT_FACE_VALUE and out.candidates:
                typer.echo("      candidates (code-extracted): " + " | ".join(
                    f"{x.option_key}='{x.text}'" for x in out.candidates))
            if r.question_id == SELECT_FACE_VALUE and out.selected is not None:
                typer.echo(f"      face value (inferred, copied from code-extracted candidate "
                           f"'{out.selected.text}' in {out.selected.found_in}): {out.selected.value} "
                           f"{out.selected.currency}; observed: {c.observed_face_value}")
        if c.route_key in statuses:
            v = advisory_view(statuses[c.route_key], out.signals.values())
            typer.echo(f"    status: deterministic={v['deterministic_status']} advisory={v['advisory_status']}")
    typer.echo(rep.model_dump_json())


@app.command()
def worker(once: bool = typer.Option(False, "--once", help="one scheduler tick, then exit"),
           cycles: Optional[int] = typer.Option(None, "--cycles", help="number of ticks")) -> None:
    """Scheduler: DB lease (no overlap), persistent job state, bounded catch-up, heartbeat file."""
    ctx = _ctx()
    run_forever(ctx, max_cycles=1 if once else cycles)


@app.command()
def health(as_json: bool = typer.Option(False, "--json", help="compact single-line JSON (for watchers)")) -> None:
    """Print worker/source health; exit code 1 when stale/failing (for cron/external watchers)."""
    from .health import compute_health
    ctx = _ctx(init=False)  # lightweight: no migrations, read-only queries
    with ctx.session_factory() as s:
        body, code = compute_health(s, ctx.settings, utcnow())
    if as_json:
        typer.echo(json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str))
    else:
        typer.echo(json.dumps(body, indent=2, ensure_ascii=False, default=str))
    raise typer.Exit(code=0 if code == 200 else 1)


@app.command()
def backup(keep: int = typer.Option(None, help="override VALUE_RAIL_BACKUP_KEEP"),
           restore_check: bool = typer.Option(True, "--restore-test/--no-restore-test")) -> None:
    """Online SQLite backup to data/backups (+ restore test into a temp file, compares row counts)."""
    from .backup import create_backup, restore_test, run_backup_job
    ctx = _ctx()
    if restore_check and keep is None:
        info = run_backup_job(ctx.settings)
    else:
        info = create_backup(ctx.settings, keep=keep)
        if restore_check:
            info["restore_test"] = restore_test(Path(info["backup"]))
            info["ok"] = info["restore_test"]["ok"]
        else:
            info["ok"] = True
    typer.echo(json.dumps(info, indent=2, default=str))
    raise typer.Exit(code=0 if info.get("ok") else 1)


@app.command("restore-test")
def restore_test_cmd(backup_file: Path = typer.Argument(None, help="backup file (default: newest)")) -> None:
    """Restore a backup into a temp file and verify integrity + row counts."""
    from .backup import list_backups, restore_test
    ctx = _ctx()
    f = backup_file or (list_backups(ctx.settings.backup_dir) or [None])[-1]
    if f is None:
        typer.echo("no backups found", err=True)
        raise typer.Exit(2)
    res = restore_test(Path(f))
    typer.echo(json.dumps(res, indent=2))
    raise typer.Exit(code=0 if res["ok"] else 1)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the mobile web UI (uvicorn)."""
    import uvicorn

    from .web.app import create_app

    ctx = _ctx()
    if host not in ("127.0.0.1", "localhost", "::1") and not ctx.settings.auth_enabled:
        typer.echo("Refusing to bind a non-local host without VALUE_RAIL_BASIC_USER/PASSWORD (and use TLS).", err=True)
        raise typer.Exit(2)
    uvicorn.run(create_app(ctx), host=host, port=port)


@rules_app.command("list")
def rules_list() -> None:
    ctx = _ctx()
    with ctx.session_factory() as s:
        for r in s.scalars(select(RuleVersionRow).order_by(RuleVersionRow.id)):
            typer.echo(f"#{r.id} {r.label} valid_from={to_display(r.valid_from)} {json.dumps(r.params)}")


@rules_app.command("add")
def rules_add(label: str = typer.Option(..., "--label"),
              param: list[str] = typer.Option([], "--param", help="key=value, e.g. price_find_min_discount=0.30"),
              notes: str = "") -> None:
    """Add a new immutable rule version (valid from now), based on the active one."""
    ctx = _ctx()
    now = utcnow()
    with ctx.session_factory.begin() as s:
        cur = active_rule_version(s, now)
        base = rule_params_of(cur).model_dump() if cur else ctx.rule_params_from_config().model_dump()
        for p in param:
            k, _, v = p.partition("=")
            if k not in base:
                raise typer.BadParameter(f"unknown rule param {k}")
            base[k] = int(v) if isinstance(base[k], int) else (Decimal(v) if isinstance(base[k], Decimal) else v)
        base["label"] = label
        from .valuation.models import RuleParams
        row = add_rule_version(s, RuleParams.model_validate(base), valid_from=now, now=now, notes=notes)
        typer.echo(f"rule version #{row.id} {row.label} active from {to_display(row.valid_from)}")


if __name__ == "__main__":
    app()
