"""Derive a fee/proceeds projection from a sourced ExitRule (no network).

Only used when the connector itself has no exit capability. The derived quote is stamped with the
evaluation time and expires at the rule's `review_by` date, so unreviewed terms turn routes `expired`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_FLOOR, Decimal

from ..connectors.base import DiscoveryItem, QuoteBundle, SourceSpec
from ..domain.enums import EvidenceKind, SourceKind, SourceRole
from ..domain.money import is_unknown
from ..evidence import EvidenceDraft
from ..valuation.models import ExitQuoteInput, ExitRule, RuleParams


def rule_source(rule: ExitRule) -> SourceSpec:
    return SourceSpec(key=f"rule-exit:{rule.key}", name=f"Exit-Regel {rule.key} (Quellen: {rule.sourced_at})",
                      kind=SourceKind.EXIT_VENUE, role=SourceRole.EXIT)


def derived_depth(rule: ExitRule, face_value) -> int | str:
    depth: int | str = rule.depth_per_request_units
    if rule.depth_limit_eur is not None and not is_unknown(face_value) and Decimal(face_value) > 0:
        by_limit = int((Decimal(rule.depth_limit_eur) / Decimal(face_value)).to_integral_value(ROUND_FLOOR))
        depth = by_limit if is_unknown(depth) else min(int(depth), by_limit)
    return depth


def exit_quote_from_rule(params: RuleParams, item: DiscoveryItem, now: datetime) -> tuple[QuoteBundle | None, ExitRule | None]:
    if item.is_synthetic:
        return None, None
    rule = params.exit_rule_for(item.product.redemption_program, item.product.region)
    if rule is None:
        return None, None
    face = item.product.face_value
    unit_price = face if (not is_unknown(face) and item.product.face_currency == rule.payout_currency) else "unknown"
    src = rule_source(rule)
    # A published request/day limit is not an executable quote or confirmed available depth.
    q = ExitQuoteInput(quote_ref="pending", venue_key=src.key, identity=item.product, unit_price=unit_price,
                       currency=rule.payout_currency, depth_quantity="unknown", fees=list(rule.fees),
                       captured_at=now, valid_until=rule.review_by)
    ev = EvidenceDraft(kind=EvidenceKind.FEE_SCHEDULE, source_key=src.key, captured_at=now,
                       scope=f"rule:{params.label}:{rule.key}",
                       summary=f"Exit-Regel {rule.key}: {rule.description}",
                       payload={"rule_label": params.label, "rule": rule.model_dump(mode="json"),
                                "projected_max_depth": derived_depth(rule, face), "executable_quote": False})
    return QuoteBundle(source=src, quote=q, evidence=[ev]), rule
