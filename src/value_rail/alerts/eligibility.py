"""Recheck pending research notifications at delivery time, without network I/O."""
from sqlalchemy import select

from ..catalog import resolve_instrument
from ..domain.enums import RouteStatus
from ..storage.orm import ProductRow, RouteEvaluationRow, SourceRow, SellerOfferRow
from ..storage.repo import active_rule_version, rule_params_of
from ..valuation.engine import evaluate_route
from ..valuation.current import with_current_prerequisites
from ..valuation.models import RouteInputs


def delivery_check(settings):
    def check(s, alert, now):
        cfg = settings.file_config
        if alert.payload.get("status") not in cfg.alerts.alert_statuses:
            return False, "status_no_longer_alertable"
        if not cfg.scope.enabled and cfg.rules.evaluation_mode != "screener":
            return True, "eligible"
        if alert.is_synthetic:
            return False, "synthetic_not_a_real_route"
        if alert.route_key.startswith("coingate:clearance:") or any(c.enabled and c.kind == "coingate_clearance" for c in cfg.connectors):
            listing = s.scalar(select(SellerOfferRow).where(SellerOfferRow.source_key == "coingate", SellerOfferRow.offer_key == alert.route_key))
            if not alert.route_key.startswith("coingate:clearance:") or listing is None or not listing.active:
                return False, "clearance_listing_no_longer_available"
        original = s.get(RouteEvaluationRow, alert.route_evaluation_id)
        latest = s.scalar(select(RouteEvaluationRow).where(RouteEvaluationRow.route_key == alert.route_key)
                          .order_by(RouteEvaluationRow.evaluated_at.desc(), RouteEvaluationRow.id.desc()).limit(1))
        rv = active_rule_version(s, now)
        if original is None or latest is None or rv is None:
            return False, "missing_evaluation_or_rules"
        params = rule_params_of(rv)
        for ev in (original, latest):
            if ev.is_synthetic:
                return False, "synthetic_not_a_real_route"
            inp = RouteInputs.model_validate(ev.inputs)
            if params.evaluation_mode == "route":
                inp = with_current_prerequisites(s, ev, inp, settings)
            product = s.get(ProductRow, ev.product_id) if ev.product_id else None
            if cfg.scope.enabled and resolve_instrument(inp.product.redemption_program, inp.product.variant,
                                  product.product_family if product else "") is None:
                return False, "outside_liquid_value_scope"
            result = evaluate_route(inp.model_copy(update={"evaluated_at": now}), params)
            if params.evaluation_mode == "screener":
                if cfg.scope.allowed_source_keys and result.screening.get("source_key") not in cfg.scope.allowed_source_keys:
                    return False, "source_no_longer_monitored"
                if result.status != RouteStatus.PRICE_FIND:
                    return False, "listing_no_longer_fresh_discounted_and_available"
                if ev.id == latest.id and result.screening != original.outputs.get("screening"):
                    # A later scan of the same listing may have a newer timestamp. Compare its offer facts.
                    fields = ("listing_price", "face_value", "currency", "face_currency", "seller", "region", "product", "listing_url")
                    if any(result.screening.get(k) != original.outputs.get("screening", {}).get(k) for k in fields):
                        return False, "listing_changed_since_signal"
            elif result.status != RouteStatus.VERIFIED_ROUTE or result.profit_eur <= 0:
                return False, "route_no_longer_fresh_verified_and_profitable"
            keys = ([result.screening["source_key"]] if result.screening else [o.source_key for o in inp.offers])
            if params.evaluation_mode == "route" and inp.checkout_quote:
                keys.append(inp.checkout_quote.source_key)
            if params.evaluation_mode == "route" and inp.exit_quote:
                keys.append(inp.exit_quote.venue_key)
            if s.scalar(select(SourceRow.id).where(SourceRow.key.in_(keys), SourceRow.health == "down").limit(1)):
                return False, "source_down"
        return True, "eligible"
    return check
