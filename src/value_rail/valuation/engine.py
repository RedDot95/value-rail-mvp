"""Route valuation engine (pure functions, Decimal only).

Formulas (Bauauftrag, implemented exactly):
    discount      = 1 - all_in_purchase_eur / face_value_reference_eur
    profit_eur(q) = net_exit_eur(q) - acquisition_cost_eur(q)
    edge(q)       = profit_eur(q) / acquisition_cost_eur(q)

Status precedence:
    1. any hard block (identity, unknown currency, unknown required fee, aggregator-only price) -> blocked
    2. complete + fresh route evidence, edge >= min_edge AND profit >= min_profit -> verified_route
       complete + fresh but below threshold                                     -> no_signal
    3. complete route evidence but a quote/offer is stale                        -> expired
    4. price-basis offer itself stale                                            -> expired
    5. proven nominal discount >= price_find_min_discount                        -> price_find
    6. otherwise                                                                 -> no_signal
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, localcontext

from ..domain.enums import PrereqStatus, RouteStatus, SourceRole
from ..domain.money import MONEY_CONTEXT, is_unknown
from .models import (BreakdownLine, CheckoutQuoteInput, EvaluationResult, ExitQuoteInput, FeeComponent,
                     OfferInput, RouteInputs, RuleParams)

ENGINE_VERSION = "1.2.0"  # Comparable all-in price selection and FX freshness/validity checks.


class UnknownFeeError(ValueError):
    pass


def nominal_discount(all_in_purchase_eur: Decimal, face_value_reference_eur: Decimal) -> Decimal:
    with localcontext(MONEY_CONTEXT):
        if face_value_reference_eur <= 0:
            raise ValueError("face value reference must be > 0")
        return Decimal(1) - (all_in_purchase_eur / face_value_reference_eur)


def unknown_required_fees(fees: list[FeeComponent]) -> list[str]:
    return [f.name for f in fees if f.required and not f.included_in_quote and is_unknown(f.amount)]


def _apply_fees(base: Decimal, q: int, fees: list[FeeComponent], lines: list[BreakdownLine]) -> Decimal:
    total = Decimal(0)
    for f in fees:
        if f.included_in_quote:
            lines.append(BreakdownLine(label=f.name, amount_eur=Decimal("0.00"), note="im Quote enthalten - nicht doppelt"))
            continue
        if is_unknown(f.amount):
            if f.required:
                raise UnknownFeeError(f.name)
            lines.append(BreakdownLine(label=f.name, amount_eur="unknown", note="optional, nicht angesetzt"))
            continue
        amt = Decimal(f.amount)
        if f.kind == "fixed_per_order":
            v = amt
        elif f.kind == "fixed_per_unit":
            v = amt * q
        else:  # percent of base amount (optionally capped per unit)
            v = base * amt
            if f.cap_per_unit is not None and q > 0:
                per_unit = min((base / q) * amt, Decimal(f.cap_per_unit))
                v = per_unit * q
        note = f.kind if f.cap_per_unit is None else f"{f.kind} (max {f.cap_per_unit} EUR/Einheit)"
        lines.append(BreakdownLine(label=f.name, amount_eur=v, note=note))
        total += v
    return total


def acquisition_cost_eur(unit_price_eur: Decimal, q: int, fees: list[FeeComponent],
                         lines: list[BreakdownLine] | None = None) -> Decimal:
    with localcontext(MONEY_CONTEXT):
        lines = lines if lines is not None else []
        base = unit_price_eur * q
        lines.append(BreakdownLine(label=f"Kaufpreis {q} x {unit_price_eur}", amount_eur=base))
        return base + _apply_fees(base, q, fees, lines)


def net_exit_eur(unit_price_eur: Decimal, q: int, fees: list[FeeComponent],
                 lines: list[BreakdownLine] | None = None) -> Decimal:
    with localcontext(MONEY_CONTEXT):
        lines = lines if lines is not None else []
        gross = unit_price_eur * q
        lines.append(BreakdownLine(label=f"Exit brutto {q} x {unit_price_eur}", amount_eur=gross))
        return gross - _apply_fees(gross, q, fees, lines)


def _age_s(captured_at: datetime, now: datetime) -> float:
    return (now - captured_at).total_seconds()


def _is_stale(captured_at: datetime, valid_until, now: datetime, max_age: int) -> bool:
    if _age_s(captured_at, now) > max_age:
        return True
    return not is_unknown(valid_until) and valid_until < now


def _rate(currency: str, inputs: RouteInputs) -> Decimal | None:
    if currency == "EUR":
        return Decimal(1)
    matches = [fx for fx in inputs.fx_rates if fx.currency == currency]
    return Decimal(max(matches, key=lambda fx: fx.captured_at).rate_to_eur) if matches else None


def _fx_stale(currency: str, inputs: RouteInputs, rule: RuleParams) -> bool:
    matches = [fx for fx in inputs.fx_rates if fx.currency == currency]
    return currency != "EUR" and bool(matches) and \
        _age_s(max(matches, key=lambda fx: fx.captured_at).captured_at, inputs.evaluated_at) > rule.max_quote_age_seconds


def _currency_block(currency: str, inputs: RouteInputs, what: str) -> tuple[Decimal | None, str | None]:
    if is_unknown(currency) or not currency:
        return None, f"currency_unknown:{what}"
    r = _rate(currency, inputs)
    if r is None:
        return None, f"fx_rate_missing:{what}:{currency}"
    if not r.is_finite() or r <= 0:
        return None, f"fx_rate_invalid:{what}:{currency}"
    return r, None


def _select_price_basis(inp: RouteInputs, rule: RuleParams) -> tuple[OfferInput | None, list[dict[str, str]], list[str], list[str]]:
    ignored: list[dict[str, str]] = []
    notes: list[str] = []
    candidates: list[OfferInput] = []
    discovery_matches: list[OfferInput] = []
    for o in inp.offers:
        mm = inp.product.mismatches(o.identity)
        if mm:
            ignored.append({"offer_ref": o.offer_ref, "reason": "identity_mismatch:" + ",".join(mm)})
            continue
        if o.source_role != SourceRole.PRICE_BASIS:
            discovery_matches.append(o)
            ignored.append({"offer_ref": o.offer_ref, "reason": "discovery_only_source (Aggregator, kein Preisnachweis)"})
            notes.append(f"Aggregator-Preis {o.unit_price} {o.currency} ({o.source_key}) nur Discovery - nicht als Kaufpreis verwendet")
            continue
        candidates.append(o)
    if not candidates:
        if discovery_matches:
            return None, ignored, ["direct_price_unverified:only_discovery_only_offers"], notes
        if inp.offers:
            return None, ignored, ["no_offer_matching_identity"], notes
        return None, ignored, ["no_offer"], notes
    def price_rank(o: OfferInput) -> tuple[bool, bool, Decimal]:
        rate, block = _currency_block(o.currency, inp, "offer")
        fees = [] if o.price_includes_fees else o.fees
        if block or is_unknown(o.unit_price) or unknown_required_fees(fees):
            return True, True, Decimal(0)
        stale = _age_s(o.captured_at, inp.evaluated_at) > rule.max_offer_age_seconds or _fx_stale(o.currency, inp, rule)
        return False, stale, acquisition_cost_eur(Decimal(o.unit_price) * rate, 1, fees)

    # Compare proven all-in EUR amounts; nominal prices in different currencies
    # or with different fees are not comparable. Prefer fresh usable evidence.
    chosen = min(candidates, key=price_rank)
    return chosen, ignored, [], notes


def evaluate_route(inp: RouteInputs, rule: RuleParams) -> EvaluationResult:
    with localcontext(MONEY_CONTEXT):
        return _evaluate(inp, rule)


def _evaluate(inp: RouteInputs, rule: RuleParams) -> EvaluationResult:
    now = inp.evaluated_at
    out: dict = {"route_key": inp.route_key, "engine_version": ENGINE_VERSION, "rule_label": rule.label}
    blocks: list[str] = []
    stale: list[str] = []
    v_missing: list[str] = []
    notes: list[str] = []

    offer, ignored, sel_blocks, sel_notes = _select_price_basis(inp, rule)
    out["ignored_offers"] = ignored
    blocks += sel_blocks
    notes += sel_notes

    nominal_fx_stale = False

    def check_fx(currency: str, what: str, *, nominal: bool = False) -> None:
        nonlocal nominal_fx_stale
        if _fx_stale(currency, inp, rule):
            stale.append(f"fx_rate_stale:{what}:{currency}")
            nominal_fx_stale |= nominal

    # face value reference in EUR
    face_eur: Decimal | None = None
    if is_unknown(inp.product.face_value):
        blocks.append("face_value_unknown")
    else:
        check_fx(inp.product.face_currency, "face_value", nominal=True)
        r, b = _currency_block(inp.product.face_currency, inp, "face_value")
        if b:
            blocks.append(b)
        else:
            face_eur = Decimal(inp.product.face_value) * r
            if face_eur <= 0:
                blocks.append("face_value_not_positive")
                face_eur = None
            else:
                out["face_value_reference_eur"] = face_eur

    unit_all_in: Decimal | None = None
    offer_rate: Decimal | None = None
    offer_fees: list[FeeComponent] = []
    if offer is not None:
        out["price_basis_offer_ref"] = offer.offer_ref
        out["advertised_quantity"] = offer.advertised_quantity.value
        check_fx(offer.currency, "offer", nominal=True)
        offer_rate, b = _currency_block(offer.currency, inp, "offer")
        if b:
            blocks.append(b)
        if is_unknown(offer.unit_price):
            blocks.append("offer_price_unknown")
        offer_fees = [] if offer.price_includes_fees else list(offer.fees)
        if offer.price_includes_fees and offer.fees:
            notes.append("Angebotspreis ist all-in; gelistete Gebuehren nicht erneut addiert")
        for name in unknown_required_fees(offer_fees):
            blocks.append(f"unknown_required_fee:{name}")
        if _age_s(offer.captured_at, now) > rule.max_offer_age_seconds:
            stale.append("offer_stale")
        if offer_rate is not None and not is_unknown(offer.unit_price) and not unknown_required_fees(offer_fees):
            unit_eur = Decimal(offer.unit_price) * offer_rate
            unit_all_in = acquisition_cost_eur(unit_eur, 1, offer_fees)
            out["unit_all_in_eur"] = unit_all_in
            if face_eur is not None:
                out["discount"] = nominal_discount(unit_all_in, face_eur)

    cq: CheckoutQuoteInput | None = inp.checkout_quote
    eq: ExitQuoteInput | None = inp.exit_quote
    cq_rate = eq_rate = None
    cq_usable_qty = False

    if cq is None:
        v_missing.append("checkout_quote")
    else:
        check_fx(cq.currency, "checkout_quote")
        mm = inp.product.mismatches(cq.identity)
        if mm:
            blocks.append("checkout_quote_identity_mismatch:" + ",".join(mm))
        cq_rate, b = _currency_block(cq.currency, inp, "checkout_quote")
        if b:
            blocks.append(b)
        for name in unknown_required_fees(cq.fees):
            blocks.append(f"unknown_required_fee:{name}")
        cq_stale = _is_stale(cq.captured_at, cq.valid_until, now, rule.max_quote_age_seconds)
        if cq_stale:
            stale.append("checkout_quote_stale")
        if is_unknown(cq.unit_price):
            v_missing.append("checkout_unit_price")
        if is_unknown(cq.quantity_confirmed) or int(cq.quantity_confirmed) <= 0:
            v_missing.append("checkout_confirmed_quantity")
        elif not mm and not cq_stale:
            cq_usable_qty = True

    if eq is None:
        v_missing.append("exit_quote")
    else:
        check_fx(eq.currency, "exit_quote")
        mm = inp.product.mismatches(eq.identity)
        if mm:
            blocks.append("exit_quote_identity_mismatch:" + ",".join(mm))
        eq_rate, b = _currency_block(eq.currency, inp, "exit_quote")
        if b:
            blocks.append(b)
        for name in unknown_required_fees(eq.fees):
            blocks.append(f"unknown_required_fee:{name}")
        if _is_stale(eq.captured_at, eq.valid_until, now, rule.max_quote_age_seconds):
            stale.append("exit_quote_stale")
        if is_unknown(eq.unit_price):
            v_missing.append("exit_price")
        if is_unknown(eq.depth_quantity) or int(eq.depth_quantity) <= 0:
            v_missing.append("exit_depth")

    for p in inp.prerequisites:
        if p.status != PrereqStatus.PROVEN:
            v_missing.append(f"prerequisite:{p.name}")

    # ---- proven quantity (never the advertised number) ----
    if offer is not None:
        if cq_usable_qty:
            pq, scope = int(cq.quantity_confirmed), "checkout_confirmed"
        elif not is_unknown(offer.checkout_confirmed_quantity.value):
            pq, scope = int(offer.checkout_confirmed_quantity.value), offer.checkout_confirmed_quantity.scope or "checkout_confirmed"
        elif not is_unknown(offer.purchased_quantity.value):
            pq, scope = int(offer.purchased_quantity.value), offer.purchased_quantity.scope or "historical_purchase"
        else:
            pq, scope = None, "unknown"
        if pq is not None:
            out["proven_quantity"] = pq
            out["proven_quantity_scope"] = scope
            if face_eur is not None:
                out["face_total_eur"] = face_eur * pq
            if offer_rate is not None and not is_unknown(offer.unit_price) and not unknown_required_fees(offer_fees):
                out["cost_total_eur"] = acquisition_cost_eur(Decimal(offer.unit_price) * offer_rate, pq, offer_fees)
            adv = offer.advertised_quantity.value
            if not is_unknown(adv) and int(adv) > pq:
                notes.append(f"{adv} angezeigt, nur {pq} nachgewiesen ({scope}); Restkapazitaet und Ursache offen")
        # remaining capacity and its cause are never inferred from the advertised number
        out["remaining_capacity"] = "unknown"
        out["capacity_limit_cause"] = "unknown"

    # ---- route economics (only when the full chain is present) ----
    route_complete = not v_missing and cq is not None and eq is not None and cq_rate is not None and eq_rate is not None
    profit = edge = None
    if route_complete and not blocks:
        q = min(int(cq.quantity_confirmed), int(eq.depth_quantity))
        if q < int(cq.quantity_confirmed):
            notes.append(f"Nur nachgewiesene Exit-Tiefe bewertet: {q} von {cq.quantity_confirmed} Einheiten")
        acq_lines: list[BreakdownLine] = []
        exit_lines: list[BreakdownLine] = []
        acq = acquisition_cost_eur(Decimal(cq.unit_price) * cq_rate, q, list(cq.fees), acq_lines)
        net = net_exit_eur(Decimal(eq.unit_price) * eq_rate, q, list(eq.fees), exit_lines)
        out.update(evaluated_quantity=q, acquisition_cost_eur=acq, net_exit_eur=net,
                   cost_breakdown=acq_lines, exit_breakdown=exit_lines)
        if acq <= 0:
            blocks.append("acquisition_cost_not_positive")
        else:
            profit = net - acq
            edge = profit / acq
            out.update(profit_eur=profit, edge=edge)

    # ---- status ----
    discount = out.get("discount")
    if blocks:
        status = RouteStatus.BLOCKED
    elif route_complete and not stale and profit is not None:
        if edge >= rule.verified_min_edge and profit >= rule.verified_min_profit_eur:
            status = RouteStatus.VERIFIED_ROUTE
        else:
            status = RouteStatus.NO_SIGNAL
            notes.append("Route vollstaendig belegt, aber unter Schwelle (Edge/Profit)")
    elif (route_complete and stale) or "offer_stale" in stale or nominal_fx_stale:
        status = RouteStatus.EXPIRED
    elif discount is not None and discount >= rule.price_find_min_discount:
        status = RouteStatus.PRICE_FIND
    else:
        status = RouteStatus.NO_SIGNAL

    # profit/edge are only ever computed for a complete, unblocked route (see above):
    # a Preisfund or blocked evaluation therefore never claims an EUR profit.
    out.update(status=status, missing_evidence=v_missing, block_reasons=blocks,
               stale_reasons=stale, notes=notes)
    return EvaluationResult(**out)
