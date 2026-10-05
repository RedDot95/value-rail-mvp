"""Sourced exit rules (Delivery 2): capped refund fee, derived depth, unknown stays blocking."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from value_rail.connectors.base import DiscoveryItem, SourceSpec
from value_rail.domain.enums import SourceKind, SourceRole
from value_rail.domain.identity import ProductIdentity
from value_rail.valuation.engine import evaluate_route, net_exit_eur
from value_rail.valuation.models import (CheckoutQuoteInput, FeeComponent, OfferInput, Prerequisite, RouteInputs,
                                         RuleParams)
from value_rail.worker.exit_rules import exit_quote_from_rule

from .conftest import make_settings

NOW = datetime(2026, 10, 5, 22, 0, tzinfo=UTC)
SRC = SourceSpec(key="recharge-com-de", name="x", kind=SourceKind.DIRECT_SELLER, role=SourceRole.PRICE_BASIS)


def params(tmp_path) -> RuleParams:
    return RuleParams.model_validate(make_settings(tmp_path).file_config.rules.model_dump())


def ident(face: str, program: str) -> ProductIdentity:
    return ProductIdentity(face_value=Decimal(face), face_currency="EUR", region="DE", variant=f"digital-code:{face}-eur",
                           seller="recharge.com", redemption_program=program)


def item(face: str, program: str, synthetic=False) -> DiscoveryItem:
    return DiscoveryItem(route_key=f"t:{program}:{face}", product=ident(face, program), product_family=program,
                         sources=[SRC], is_synthetic=synthetic)


def test_capped_percent_fee():
    fee = FeeComponent(name="refund", kind="percent", amount=Decimal("0.05"), cap_per_unit=Decimal("5.00"))
    assert net_exit_eur(Decimal("150"), 2, [fee]) == Decimal("290.00")  # 2 x min(7.50, 5.00)
    assert net_exit_eur(Decimal("50"), 1, [fee]) == Decimal("47.50")
    uncapped = FeeComponent(name="refund", kind="percent", amount=Decimal("0.05"))
    assert net_exit_eur(Decimal("150"), 2, [uncapped]) == Decimal("285.00")


def test_rules_are_sourced(tmp_path):
    p = params(tmp_path)
    assert {r.key for r in p.exit_rules} == {"paysafecard-de-issuer-refund", "bitsa-free-plan-sepa-out"}
    for r in p.exit_rules:
        assert r.sources and all("2026-10-05" in s for s in r.sources)
        assert r.review_by != "unknown"
        for f in r.fees:
            assert f.evidence_ref != "unknown"


def test_paysafecard_rule_quote(tmp_path):
    b, rule = exit_quote_from_rule(params(tmp_path), item("150", "paysafecard"), NOW)
    q = b.quote
    assert rule.key == "paysafecard-de-issuer-refund" and q.unit_price == Decimal("150") and q.depth_quantity == 1
    assert b.source.role == SourceRole.EXIT and b.evidence[0].payload["rule"]["key"] == rule.key


def test_no_rule_for_synthetic_or_unknown_program(tmp_path):
    assert exit_quote_from_rule(params(tmp_path), item("50", "paysafecard", synthetic=True), NOW) == (None, None)
    assert exit_quote_from_rule(params(tmp_path), item("50", "azteco"), NOW) == (None, None)


def _route(tmp_path, face: str, program: str, checkout_unit: str) -> RouteInputs:
    p = params(tmp_path)
    b, rule = exit_quote_from_rule(p, item(face, program), NOW)
    cq = CheckoutQuoteInput(quote_ref="quote:hyp", source_key="recharge-com-de", identity=ident(face, program),
                            unit_price=Decimal(checkout_unit), currency="EUR", quantity_confirmed=1, captured_at=NOW)
    off = OfferInput(offer_ref="offer_snapshot:hyp", source_key="recharge-com-de", source_role="price_basis",
                     identity=ident(face, program), unit_price=Decimal(checkout_unit), currency="EUR",
                     price_includes_fees=True, captured_at=NOW)
    return RouteInputs(route_key="hyp", product=ident(face, program), offers=[off], checkout_quote=cq,
                       exit_quote=b.quote.model_copy(update={"quote_ref": "quote:rule"}),
                       prerequisites=[Prerequisite(name=n, status="proven") for n in rule.prerequisites],
                       evaluated_at=NOW), p


def test_hypothetical_paysafecard_route_at_face_is_negative(tmp_path):
    # HYPOTHETICAL: even with a proven checkout at face value (no service fee) the refund loses money.
    inp, p = _route(tmp_path, "50", "paysafecard", "50")
    res = evaluate_route(inp, p)
    assert res.status == "no_signal" and res.profit_eur == Decimal("-2.50")


def test_bitsa_rule_unknown_reload_fee_blocks_verification(tmp_path):
    inp, p = _route(tmp_path, "100", "bitsa", "50")  # even a 50 % discount cannot verify with unknown fee
    res = evaluate_route(inp, p)
    assert res.status == "blocked" and "unknown_required_fee:bitsa_voucher_reload_fee" in res.block_reasons
    assert res.profit_eur == "unknown"
