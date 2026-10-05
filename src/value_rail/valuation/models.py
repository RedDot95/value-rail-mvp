"""Self-contained valuation inputs/outputs.

`RouteInputs` contains EVERYTHING the engine needs (including the evaluation clock), so a
stored inputs JSON + the stored RuleVersion params reproduce the exact same output.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..domain.entities import QuantityObservation
from ..domain.enums import PrereqStatus, RouteStatus, SourceRole
from ..domain.identity import ProductIdentity
from ..domain.money import Dec, MaybeDecimal, MaybeInt, UnknownT


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FeeComponent(_M):
    name: str
    kind: Literal["fixed_per_order", "fixed_per_unit", "percent"]
    amount: MaybeDecimal  # EUR for fixed kinds; fraction (0.015 = 1.5 %) for percent
    required: bool = True
    included_in_quote: bool = False  # already contained in the quoted price -> never added again
    evidence_ref: str = "unknown"


class OfferInput(_M):
    offer_ref: str
    source_key: str
    source_role: SourceRole
    identity: ProductIdentity
    unit_price: MaybeDecimal
    currency: str
    price_includes_fees: bool = False
    fees: list[FeeComponent] = Field(default_factory=list)
    advertised_quantity: QuantityObservation = QuantityObservation()
    checkout_confirmed_quantity: QuantityObservation = QuantityObservation()
    purchased_quantity: QuantityObservation = QuantityObservation()
    captured_at: datetime
    evidence_refs: list[str] = Field(default_factory=list)


class CheckoutQuoteInput(_M):
    quote_ref: str
    source_key: str
    identity: ProductIdentity
    unit_price: MaybeDecimal  # checkout unit price (before listed fees unless included)
    currency: str
    quantity_confirmed: MaybeInt
    fees: list[FeeComponent] = Field(default_factory=list)
    captured_at: datetime
    valid_until: datetime | UnknownT = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)


class ExitQuoteInput(_M):
    quote_ref: str
    venue_key: str
    identity: ProductIdentity
    unit_price: MaybeDecimal  # EUR proceeds per unit before listed exit fees
    currency: str
    depth_quantity: MaybeInt  # proven depth; evaluation never exceeds it
    fees: list[FeeComponent] = Field(default_factory=list)
    captured_at: datetime
    valid_until: datetime | UnknownT = "unknown"
    evidence_refs: list[str] = Field(default_factory=list)


class Prerequisite(_M):
    name: str
    status: PrereqStatus
    evidence_ref: str = "unknown"


class FxRate(_M):
    currency: str
    rate_to_eur: Dec
    captured_at: datetime
    quote_ref: str = "unknown"


class RouteInputs(_M):
    route_key: str
    product: ProductIdentity  # reference identity the route is about
    offers: list[OfferInput] = Field(default_factory=list)
    checkout_quote: CheckoutQuoteInput | None = None
    exit_quote: ExitQuoteInput | None = None
    prerequisites: list[Prerequisite] = Field(default_factory=list)
    fx_rates: list[FxRate] = Field(default_factory=list)
    evaluated_at: datetime
    is_synthetic: bool = False


class RuleParams(_M):
    label: str = "default"
    price_find_min_discount: Dec = Decimal("0.25")
    verified_min_edge: Dec = Decimal("0.10")
    verified_min_profit_eur: Dec = Decimal("1.00")
    max_quote_age_seconds: int = 900
    max_offer_age_seconds: int = 3600


class BreakdownLine(_M):
    label: str
    amount_eur: MaybeDecimal
    note: str = ""


class EvaluationResult(_M):
    route_key: str
    status: RouteStatus
    engine_version: str
    rule_label: str
    price_basis_offer_ref: str | UnknownT = "unknown"
    ignored_offers: list[dict[str, str]] = Field(default_factory=list)
    # nominal side (Preisfund)
    unit_all_in_eur: MaybeDecimal = "unknown"
    face_value_reference_eur: MaybeDecimal = "unknown"
    discount: MaybeDecimal = "unknown"
    advertised_quantity: MaybeInt = "unknown"
    proven_quantity: MaybeInt = "unknown"
    proven_quantity_scope: str = "unknown"
    face_total_eur: MaybeDecimal = "unknown"
    cost_total_eur: MaybeDecimal = "unknown"
    remaining_capacity: MaybeInt = "unknown"
    capacity_limit_cause: str = "unknown"
    # route side (Verifizierte Route)
    evaluated_quantity: MaybeInt = "unknown"
    acquisition_cost_eur: MaybeDecimal = "unknown"
    net_exit_eur: MaybeDecimal = "unknown"
    profit_eur: MaybeDecimal = "unknown"
    edge: MaybeDecimal = "unknown"
    cost_breakdown: list[BreakdownLine] = Field(default_factory=list)
    exit_breakdown: list[BreakdownLine] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    block_reasons: list[str] = Field(default_factory=list)
    stale_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def canonical(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
