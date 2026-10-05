"""CLI for dev / replay / diagnose. Entry point: `value-rail` (or `python -m value_rail.cli`)."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

import typer
from sqlalchemy import func, select

from .alerts.dispatcher import dispatch_pending
from .alerts.sinks import build_sink
from .connectors.registry import describe_connectors
from .domain.enums import STATUS_LABEL_DE, RouteStatus
from .domain.money import fmt_eur, fmt_pct
from .domain.timeutil import to_display, utcnow
from .logging_setup import configure_logging
from .services import AppContext
from .storage.orm import AlertRow, RouteEvaluationRow, RuleVersionRow, ScanRunRow, SourceRow
from .storage.repo import active_rule_version, add_rule_version, latest_evaluations, rule_params_of
from .valuation.replay import replay_evaluation
from .worker.scheduler import run_cycle, run_forever

app = typer.Typer(help="Value Rail MVP - Delivery 1 (OFFLINE, synthetic fixtures only; no live scanning, no purchases)",
                  no_args_is_help=True)
rules_app = typer.Typer(help="Versioned valuation rules")
app.add_typer(rules_app, name="rules")


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


app.command("scan", help="Alias of load-fixtures (Delivery 1 has only the offline fixture connector).")(load_fixtures)


@app.command()
def dispatch() -> None:
    """Send pending outbox alerts via the configured sink (log)."""
    ctx = _ctx()
    cfg = ctx.settings.file_config.alerts
    rep = dispatch_pending(ctx.session_factory, build_sink(cfg.sink, ctx.settings.effective_alert_log_file), utcnow(),
                           backoff_seconds=cfg.retry_backoff_seconds)
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
            "live_scanning": False,
            "rule_version": (lambda r: {"id": r.id, "label": r.label, "params": r.params} if r else None)(active_rule_version(s, utcnow())),
            "counts": {t.__tablename__: s.scalar(select(func.count()).select_from(t)) for t in
                       (SourceRow, ScanRunRow, RouteEvaluationRow, AlertRow, RuleVersionRow)},
            "outbox": dict(s.execute(select(AlertRow.state, func.count()).group_by(AlertRow.state)).all()),
            "sources": [{"key": x.key, "health": x.health, "last_error": x.last_error} for x in s.scalars(select(SourceRow))],
            "last_scan": (lambda r: {"id": r.id, "status": r.status, "at": to_display(r.started_at),
                                     "failed": r.sources_failed} if r else None)(
                s.scalar(select(ScanRunRow).order_by(ScanRunRow.id.desc()).limit(1))),
            "connectors": describe_connectors(st),
            "scan_intervals": st.file_config.scan_intervals.model_dump(),
        }
    typer.echo(json.dumps(info, indent=2, default=str, ensure_ascii=False))


@app.command()
def worker(once: bool = typer.Option(False, "--once"), cycles: Optional[int] = typer.Option(None, "--cycles")) -> None:
    """Scheduler STUB: runs the offline fixture scan on the watchlist interval."""
    ctx = _ctx()
    run_forever(ctx, max_cycles=1 if once else cycles)


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
