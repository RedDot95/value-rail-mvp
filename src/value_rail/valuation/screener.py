"""Observed listing discounts. No checkout, account, fee or payout assumptions."""
from decimal import Decimal
from urllib.parse import urlsplit

from ..domain.enums import RouteStatus
from ..domain.money import is_unknown
from .models import EvaluationResult, RouteInputs, RuleParams


def safe_listing_url(value: str | None) -> str | None:
    try:
        url = urlsplit(value or "")
        if url.scheme == "https" and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return None


def evaluate_screener(inp: RouteInputs, rule: RuleParams) -> EvaluationResult:
    base = dict(route_key=inp.route_key, engine_version="screener/1.0.0", rule_label=rule.label)
    candidates, ignored, stale = [], [], []
    def rate(currency):
        if currency.upper() == "EUR":
            return Decimal(1)
        valid = [r for r in inp.fx_rates if r.currency.upper() == currency.upper() and r.quote_ref != "unknown"
                 and 0 <= (inp.evaluated_at - r.captured_at).total_seconds() <= rule.screener_fx_max_age_seconds
                 and r.rate_to_eur > 0]
        return max(valid, key=lambda r: r.captured_at).rate_to_eur if valid else None
    def ratio(offer):
        if offer.currency.upper() == offer.identity.face_currency.upper():
            return offer.unit_price / offer.identity.face_value
        return offer.unit_price * rate(offer.currency) / (offer.identity.face_value * rate(offer.identity.face_currency))
    for offer in inp.offers:
        reason = None
        age = (inp.evaluated_at - offer.captured_at).total_seconds()
        if offer.source_role not in ("price_basis", "discovery_only"):
            reason = "not_a_listing_source"
        elif offer.identity.key() != inp.product.key():
            reason = "different_product_identity"
        elif age < 0 or age > rule.max_offer_age_seconds:
            reason = "listing_not_fresh"
            stale.append(f"{offer.offer_ref}: {reason}")
        elif offer.valid_until is not None and offer.valid_until <= inp.evaluated_at:
            reason = "listing_expired"
            stale.append(f"{offer.offer_ref}: {reason}")
        elif not inp.is_synthetic and not offer.evidence_refs:
            reason = "listing_evidence_missing"
        elif is_unknown(offer.unit_price) or is_unknown(offer.identity.face_value):
            reason = "concrete_price_or_denomination_missing"
        elif offer.currency.upper() == "UNKNOWN" or (offer.currency.upper() != offer.identity.face_currency.upper() and
                 (rate(offer.currency) is None or rate(offer.identity.face_currency) is None)):
            reason = "price_and_face_currency_differ"
        elif offer.unit_price <= 0 or offer.identity.face_value <= 0:
            reason = "nonpositive_amount"
        elif offer.advertised_quantity.value == 0:
            reason = "out_of_stock"
        if reason:
            ignored.append(dict(offer_ref=offer.offer_ref, reason=reason))
        else:
            candidates.append(offer)
    if not candidates:
        return EvaluationResult(**base, status=RouteStatus.EXPIRED if stale else RouteStatus.BLOCKED,
                                ignored_offers=ignored, stale_reasons=stale,
                                block_reasons=[] if stale else ["concrete_available_listing_required"])
    offer = min(candidates, key=ratio)
    discount = Decimal(1) - ratio(offer)
    status = RouteStatus.PRICE_FIND if discount > 0 and discount >= rule.price_find_min_discount else RouteStatus.NO_SIGNAL
    screening = dict(listing_price=str(offer.unit_price), face_value=str(offer.identity.face_value),
                     currency=offer.currency.upper(), face_currency=offer.identity.face_currency.upper(), fx_used=offer.currency.upper() != offer.identity.face_currency.upper(), seller=offer.identity.seller, region=offer.identity.region,
                     title=offer.listing_title or offer.identity.redemption_program, product=offer.identity.redemption_program, variant=offer.identity.variant,
                     listing_url=safe_listing_url(offer.listing_url), source_key=offer.source_key,
                     captured_at=offer.captured_at.isoformat())
    if offer.valid_until is not None:
        screening["valid_until"] = offer.valid_until.isoformat()
    return EvaluationResult(**base, status=status, discount=discount, price_basis_offer_ref=offer.offer_ref,
                            advertised_quantity=offer.advertised_quantity.value,
                            ignored_offers=ignored, screening=screening)
