"""Valuation acceptance cases (SYNTHETIC inputs). Numbers refer to the Bauauftrag regression list."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from value_rail.domain.enums import RouteStatus
from value_rail.domain.identity import ProductIdentity
from value_rail.valuation import acquisition_cost_eur, evaluate_route, net_exit_eur, nominal_discount
from value_rail.valuation.models import FxRate

from .conftest import NOW, PRODUCT, RULE, checkout, exit_quote, fee, inputs, offer

FULL = dict(prereqs=[("synthetic_account", "proven")])


def with_fx(inp, rate="0.5", captured=NOW):
    return inp.model_copy(update={"fx_rates": [FxRate(currency="USD", rate_to_eur=Decimal(rate),
                                                    captured_at=captured)]})


def test_price_basis_compares_converted_eur_prices():
    inp = inputs(offers=[offer("40", ref="eur"), offer("60", currency="USD", ref="usd")])
    result = evaluate_route(with_fx(inp), RULE)
    assert result.price_basis_offer_ref == "usd" and result.unit_all_in_eur == Decimal("30")


def test_price_basis_compares_all_in_fees():
    inp = inputs(offers=[offer("40", ref="gross", includes=False,
                              fees=[fee("service", "fixed_per_order", "20")]),
                         offer("50", ref="all-in")])
    result = evaluate_route(inp, RULE)
    assert result.price_basis_offer_ref == "all-in" and result.unit_all_in_eur == Decimal("50")


def test_price_basis_prefers_fresh_usable_evidence():
    inp = inputs(offers=[offer("10", ref="stale", captured=NOW - timedelta(hours=2)),
                         offer("20", ref="unknown-fee", includes=False,
                               fees=[fee("service", "fixed_per_order", "unknown")]),
                         offer("50", ref="usable")])
    result = evaluate_route(inp, RULE)
    assert result.price_basis_offer_ref == "usable" and result.status == RouteStatus.PRICE_FIND


@pytest.mark.parametrize("rate", ["0", "-1"])
def test_nonpositive_fx_rate_blocks_false_discount(rate):
    result = evaluate_route(with_fx(inputs(offers=[offer(currency="USD")]), rate), RULE)
    assert result.status == RouteStatus.BLOCKED
    assert "fx_rate_invalid:offer:USD" in result.block_reasons
    assert result.discount == "unknown"


def test_stale_fx_rate_expires_price_find():
    inp = with_fx(inputs(offers=[offer("45", currency="USD")]), captured=NOW - timedelta(hours=1))
    result = evaluate_route(inp, RULE)
    assert result.status == RouteStatus.EXPIRED
    assert "fx_rate_stale:offer:USD" in result.stale_reasons


def test_stale_exit_fx_rate_expires_complete_profitable_route():
    inp = with_fx(inputs(cq=checkout(), eq=exit_quote("200", currency="USD")),
                  captured=NOW - timedelta(hours=1))
    result = evaluate_route(inp, RULE)
    assert result.profit_eur == Decimal("55") and result.status == RouteStatus.EXPIRED
    assert "fx_rate_stale:exit_quote:USD" in result.stale_reasons


def test_unused_stale_fx_does_not_expire_eur_route():
    inp = with_fx(inputs(cq=checkout(), eq=exit_quote()), captured=NOW - timedelta(hours=1))
    assert evaluate_route(inp, RULE).status == RouteStatus.VERIFIED_ROUTE


def test_newest_fx_rate_selected_independent_of_input_order():
    inp = with_fx(inputs(offers=[offer("60", currency="USD")]))
    old = FxRate(currency="USD", rate_to_eur=Decimal("2"), captured_at=NOW - timedelta(hours=1))
    for rates in ([old, *inp.fx_rates], [*inp.fx_rates, old]):
        result = evaluate_route(inp.model_copy(update={"fx_rates": rates}), RULE)
        assert result.status == RouteStatus.PRICE_FIND and result.unit_all_in_eur == Decimal("30")


@pytest.mark.parametrize("face", ["0", "-100"])
def test_nonpositive_face_value_blocks_without_crashing(face):
    product = PRODUCT.model_copy(update={"face_value": Decimal(face)})
    result = evaluate_route(inputs(product=product, offers=[offer(identity=product)]), RULE)
    assert result.status == RouteStatus.BLOCKED and "face_value_not_positive" in result.block_reasons


def test_formulas_exact_decimal():
    assert nominal_discount(Decimal("1.20"), Decimal("5")) == Decimal("0.76")
    acq = acquisition_cost_eur(Decimal("45"), 1, [])
    net = net_exit_eur(Decimal("100"), 1, [])
    assert net - acq == Decimal("55")
    assert (net - acq) / acq == Decimal(55) / Decimal(45)


def test_float_money_rejected():
    from pydantic import ValidationError

    from value_rail.valuation.models import FeeComponent
    with pytest.raises(ValidationError, match="float is not allowed"):
        FeeComponent(name="x", kind="fixed_per_order", amount=1.5)
    with pytest.raises(ValidationError):
        offer().model_validate(offer().model_dump() | {"unit_price": 45.0})


# 1
def test_case01_aggregator_price_never_used_direct_price_wins():
    face50 = PRODUCT.model_copy(update={"face_value": Decimal("50")})
    r = evaluate_route(inputs(product=face50, offers=[
        offer("36.00", role="discovery_only", identity=face50, ref="offer_snapshot:agg"),
        offer("56.00", identity=face50, ref="offer_snapshot:direct")]), RULE)
    assert r.price_basis_offer_ref == "offer_snapshot:direct"
    assert r.unit_all_in_eur == Decimal("56.00")
    assert r.discount == Decimal("-0.12")
    assert r.status == RouteStatus.NO_SIGNAL
    assert any(i["offer_ref"] == "offer_snapshot:agg" for i in r.ignored_offers)


def test_case01b_aggregator_only_is_blocked_not_a_find():
    r = evaluate_route(inputs(offers=[offer("36.00", role="discovery_only")]), RULE)
    assert r.status == RouteStatus.BLOCKED
    assert r.block_reasons == ["direct_price_unverified:only_discovery_only_offers"]
    assert r.discount == "unknown"


# 2
def test_case02_bitsa_price_find_without_profit_claim():
    p = PRODUCT.model_copy(update={"face_value": Decimal("5")})
    r = evaluate_route(inputs(product=p, offers=[offer("1.20", identity=p)]), RULE)
    assert r.discount == Decimal("0.76")
    assert r.status == RouteStatus.PRICE_FIND
    assert r.profit_eur == "unknown" and r.edge == "unknown"
    assert "exit_quote" in r.missing_evidence


# 3
def test_case03_paysafe_only_proven_quantity_counts():
    p = PRODUCT.model_copy(update={"face_value": Decimal("3")})
    r = evaluate_route(inputs(product=p, offers=[offer("1.35", identity=p, adv=11, purchased=3)]), RULE)
    assert r.status == RouteStatus.PRICE_FIND
    assert r.advertised_quantity == 11
    assert r.proven_quantity == 3 and r.proven_quantity_scope == "historical_purchase"
    assert r.face_total_eur == Decimal("9")
    assert r.cost_total_eur == Decimal("4.05")
    assert r.remaining_capacity == "unknown" and r.capacity_limit_cause == "unknown"
    assert r.profit_eur == "unknown"


# 4
def test_case04_profit_55_edge_122_percent():
    r = evaluate_route(inputs(cq=checkout("45.00", 1), eq=exit_quote("100.00", 1), **FULL), RULE)
    assert r.status == RouteStatus.VERIFIED_ROUTE
    assert r.profit_eur == Decimal("55.00")
    assert r.edge == Decimal(55) / Decimal(45)
    assert str(r.edge).startswith("1.2222222222")


# 5
@pytest.mark.parametrize("side", ["checkout", "exit", "offer"])
def test_case05_unknown_required_fee_blocks(side):
    unk = [fee("mystery_fee", "fixed_per_order", "unknown")]
    kw = dict(cq=checkout("45.00", 1, fees=unk if side == "checkout" else ()),
              eq=exit_quote("100.00", 1, fees=unk if side == "exit" else ()),
              offers=[offer("45.00", includes=False, fees=unk if side == "offer" else ())], **FULL)
    r = evaluate_route(inputs(**kw), RULE)
    assert r.status == RouteStatus.BLOCKED
    assert "unknown_required_fee:mystery_fee" in r.block_reasons
    assert r.profit_eur == "unknown"


def test_case05b_optional_unknown_fee_does_not_block():
    r = evaluate_route(inputs(cq=checkout("45.00", 1, fees=[fee("gift_wrap", "fixed_per_order", "unknown", required=False)]),
                              eq=exit_quote("100.00", 1), **FULL), RULE)
    assert r.status == RouteStatus.VERIFIED_ROUTE


# 6
def test_case06_dollar_sign_currency_unknown_blocks():
    r = evaluate_route(inputs(offers=[offer("100", currency="unknown")]), RULE)
    assert r.status == RouteStatus.BLOCKED
    assert "currency_unknown:offer" in r.block_reasons
    assert r.discount == "unknown"


def test_case06b_known_foreign_currency_without_fx_blocks():
    r = evaluate_route(inputs(offers=[offer("40", currency="USD")]), RULE)
    assert "fx_rate_missing:offer:USD" in r.block_reasons


# 8
def test_case08_stale_quote_is_not_a_current_verified_hit():
    old = NOW - timedelta(hours=2)
    r = evaluate_route(inputs(cq=checkout("45.00", 1, captured=old), eq=exit_quote("100.00", 1), **FULL), RULE)
    assert r.status == RouteStatus.EXPIRED
    assert "checkout_quote_stale" in r.stale_reasons


def test_case08_stale_exit_quote():
    old = NOW - timedelta(seconds=RULE.max_quote_age_seconds + 1)
    r = evaluate_route(inputs(cq=checkout("45.00", 1), eq=exit_quote("100.00", 1, captured=old), **FULL), RULE)
    assert r.status == RouteStatus.EXPIRED


@pytest.mark.parametrize("field,value", [("seller", "SYNTHETIC-Other-Seller"), ("variant", "physical-card"),
                                         ("region", "AT"), ("redemption_program", "SYNTHETIC-Program-B")])
def test_case08_wrong_identity_never_verified(field, value):
    other = PRODUCT.model_copy(update={field: value})
    # wrong seller/variant on the quote
    r = evaluate_route(inputs(cq=checkout("45.00", 1, identity=other), eq=exit_quote("100.00", 1), **FULL), RULE)
    assert r.status == RouteStatus.BLOCKED
    # wrong seller/variant on the offer -> offer ignored, no price basis
    r2 = evaluate_route(inputs(offers=[offer("45.00", identity=other)]), RULE)
    assert r2.status == RouteStatus.BLOCKED and r2.block_reasons == ["no_offer_matching_identity"]


def test_unproven_prerequisite_keeps_it_a_price_find():
    r = evaluate_route(inputs(cq=checkout("45.00", 1), eq=exit_quote("100.00", 1),
                              prereqs=[("synthetic_kyc", "unknown")]), RULE)
    assert r.status == RouteStatus.PRICE_FIND
    assert "prerequisite:synthetic_kyc" in r.missing_evidence
    assert r.profit_eur == "unknown"


# 9
def test_case09_only_proven_exit_depth_is_evaluated():
    p = PRODUCT.model_copy(update={"face_value": Decimal("40")})
    r = evaluate_route(inputs(product=p, offers=[offer("20.00", identity=p, adv=10)],
                              cq=checkout("20.00", 10, identity=p), eq=exit_quote("30.00", 2, identity=p), **FULL), RULE)
    assert r.evaluated_quantity == 2
    assert r.acquisition_cost_eur == Decimal("40.00")
    assert r.net_exit_eur == Decimal("60.00")
    assert r.profit_eur == Decimal("20.00")


# 10
@pytest.mark.parametrize("kind", ["fixed_per_order", "fixed_per_unit", "percent"])
@pytest.mark.parametrize("side", ["checkout", "exit"])
def test_case10_higher_fee_never_increases_profit(kind, side):
    amounts = ["0", "0.01", "0.5", "1", "2.5"] if kind != "percent" else ["0", "0.001", "0.01", "0.05", "0.2"]
    profits = []
    for a in amounts:
        f = [fee("f", kind, a)]
        r = evaluate_route(inputs(cq=checkout("45.00", 3, fees=f if side == "checkout" else ()),
                                  eq=exit_quote("100.00", 3, fees=f if side == "exit" else ()), **FULL), RULE)
        profits.append(r.profit_eur)
    assert all(b <= a for a, b in zip(profits, profits[1:])), profits
    assert profits[-1] < profits[0]


# 11
def test_case11_fee_included_in_quote_not_double_counted():
    inc = [fee("trading_fee", "percent", "0.01", included_in_quote=True)]
    exc = [fee("trading_fee", "percent", "0.01", included_in_quote=False)]
    r_inc = evaluate_route(inputs(cq=checkout("80.00", 1), eq=exit_quote("100.00", 1, fees=inc), **FULL), RULE)
    r_exc = evaluate_route(inputs(cq=checkout("80.00", 1), eq=exit_quote("100.00", 1, fees=exc), **FULL), RULE)
    assert r_inc.net_exit_eur == Decimal("100.00")
    assert r_exc.net_exit_eur == Decimal("99.0000")
    assert r_inc.profit_eur == Decimal("20.00")


def test_all_in_offer_fees_not_added_again():
    r = evaluate_route(inputs(offers=[offer("45.00", includes=True, fees=[fee("svc", "fixed_per_order", "2")])]), RULE)
    assert r.unit_all_in_eur == Decimal("45.00")


def test_thresholds_verified_requires_edge_and_min_profit():
    # 10 % edge but only 0.50 EUR profit -> not verified
    p = PRODUCT.model_copy(update={"face_value": Decimal("10")})
    r = evaluate_route(inputs(product=p, offers=[offer("5.00", identity=p)], cq=checkout("5.00", 1, identity=p),
                              eq=exit_quote("5.50", 1, identity=p), **FULL), RULE)
    assert r.edge == Decimal("0.1") and r.profit_eur == Decimal("0.50")
    assert r.status == RouteStatus.NO_SIGNAL
    # exactly 10 % and exactly 1 EUR -> verified
    r2 = evaluate_route(inputs(product=p, offers=[offer("5.00", identity=p)], cq=checkout("10.00", 1, identity=p),
                               eq=exit_quote("11.00", 1, identity=p), **FULL), RULE)
    assert r2.status == RouteStatus.VERIFIED_ROUTE


def test_price_find_threshold_25_percent():
    assert evaluate_route(inputs(offers=[offer("75.00")]), RULE).status == RouteStatus.PRICE_FIND
    assert evaluate_route(inputs(offers=[offer("75.01")]), RULE).status == RouteStatus.NO_SIGNAL


def test_unknown_identity_field_never_matches():
    p = ProductIdentity(face_value=Decimal("10"), face_currency="EUR", region="unknown", variant="v", seller="s",
                        redemption_program="r")
    r = evaluate_route(inputs(product=p, offers=[offer("1.00", identity=p)]), RULE)
    assert r.status == RouteStatus.BLOCKED
