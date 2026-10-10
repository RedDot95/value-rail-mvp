"""Explain actual search coverage and blockers without inventing a liquid exit."""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from .catalog import instruments, resolve_instrument
from .domain.enums import RouteStatus
from .storage.orm import OperatorProfileRow, ProductRow, SourceRow, SellerOfferRow
from .storage.repo import active_rule_version, latest_evaluations, rule_params_of
from .valuation.engine import evaluate_route
from .valuation.current import with_current_prerequisites
from .valuation.models import RouteInputs


def coverage_report(s, settings, now):
    cfg = settings.file_config
    rv = active_rule_version(s, now)
    params = rule_params_of(rv) if rv is not None else None
    targets = {item["key"]: set() for item in instruments()}
    sweeps = [c.key for c in cfg.connectors if c.enabled and c.kind == "coingate_clearance"]
    by_instrument = {item["key"]: {"evaluations": 0, "statuses": Counter(), "blockers": Counter()} for item in instruments()}
    sources = {x.key: x for x in s.scalars(select(SourceRow))}
    verified = []
    signals = []
    active_clearance = set(s.scalars(select(SellerOfferRow.offer_key).where(SellerOfferRow.source_key == "coingate", SellerOfferRow.active.is_(True)))) if sweeps else set()
    for ev in latest_evaluations(s):
        if sweeps and ev.route_key not in active_clearance:
            continue
        if ev.is_synthetic or (cfg.scope.allowed_source_keys and not any(
                o.get("source_key") in cfg.scope.allowed_source_keys for o in ev.inputs.get("offers", []))):
            continue
        product = s.get(ProductRow, ev.product_id) if ev.product_id else None
        inp = RouteInputs.model_validate(ev.inputs)
        if params and params.evaluation_mode == "route":
            inp = with_current_prerequisites(s, ev, inp, settings)
        item = resolve_instrument(inp.product.redemption_program, inp.product.variant,
                                  product.product_family if product else "")
        if item is None:
            continue
        # Present freshness at the time of this query, not just the stored scan timestamp.
        result = evaluate_route(inp.model_copy(update={"evaluated_at": now}), params) if params else None
        stats = by_instrument[item["key"]]
        stats["evaluations"] += 1
        stats["statuses"].update([result.status.value if result else ev.status])
        if result:
            stats["blockers"].update(result.block_reasons + result.missing_evidence + result.stale_reasons)
            source_keys = [result.screening["source_key"]] if result.screening else [o.source_key for o in inp.offers]
            if inp.checkout_quote:
                source_keys.append(inp.checkout_quote.source_key)
            if inp.exit_quote:
                source_keys.append(inp.exit_quote.venue_key)
            down = [k for k in source_keys if k in sources and sources[k].health == "down"]
            if result.screening and result.status == RouteStatus.PRICE_FIND and not down:
                signals.append({"evaluation_id": ev.id, "route_key": ev.route_key, "discount": str(result.discount), **result.screening})
            if result.status == RouteStatus.VERIFIED_ROUTE and result.profit_eur > 0 and not down:
                verified.append({"evaluation_id": ev.id, "instrument": item["key"], "route_key": ev.route_key,
                                 "profit_eur": str(result.profit_eur), "edge": str(result.edge)})
    rows = []
    for item in instruments():
        stats = by_instrument[item["key"]]
        rows.append(item | {"targeted_sources": sorted(targets[item["key"]]),
                            "observations": stats["evaluations"], "statuses": dict(stats["statuses"]),
                            "blockers": dict(stats["blockers"]),
                            "exit_rule_configured": any(r.redemption_program == item["key"] for r in params.exit_rules) if params else False})
    return {"checked_at": now.isoformat(), "goal": "liquid_value_discount_screener" if cfg.rules.evaluation_mode == "screener" else "fully_evidenced_profitable_liquid_value_routes",
            "screener_mode": cfg.rules.evaluation_mode == "screener", "candidate_signals_now": signals,
            "verified_only_alerts": cfg.alerts.alert_statuses == ["verified_route"],
            "scope_enabled": cfg.scope.enabled, "candidate_count": len(rows),
            "explicitly_targeted_count": sum(bool(r["targeted_sources"]) for r in rows),
            "category_sweeps": sorted(set(sweeps)),
            "real_operator_configured": bool(cfg.operator and s.scalar(select(OperatorProfileRow.id).where(
                OperatorProfileRow.name == cfg.operator.name, OperatorProfileRow.is_synthetic.is_(False)).limit(1))),
            "rule_label": params.label if params else None,
            "verified_min_profit_eur": str(params.verified_min_profit_eur) if params else None,
            "verified_min_edge": str(params.verified_min_edge) if params else None,
            "verified_routes_now": verified, "instruments": rows,
            "note": "Signals compare observed listing prices with denomination; payout and fees are checked manually." if cfg.rules.evaluation_mode == "screener" else "Catalogue inclusion is not proof of liquidity. Resale requires an executable buyer quote and depth; face value is not exit proceeds."}
