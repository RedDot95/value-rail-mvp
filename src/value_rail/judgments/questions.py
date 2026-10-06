"""Concrete enrichment questions (instructions + criteria + the state shape they read).

State shape (built by `service.build_state`, every string truncated to [enrichment].max_state_chars):
    {
      "offer": {"title", "description", "merchant", "source", "region", "variant", "redemption_program",
                "price_text", "observed_family"},
      "compliant_route": {"customer_region": "DE", "accepted_regions": [...]},
      "payload_snippet": "<connector payload, truncated>",              # only for looks_like_block_page
      "numeric_candidates": {"candidate_0": {"text", "found_in", "context"}, ...}  # only for select_face_value
    }

Questions follow the TypeSafe guidance (docs.typesafe.ai/primitives.md, how-to-build-with-system-one.md):
one atomic snap judgment each, backticked state paths, an explicit "other/none" escape option on every Choice,
thresholds and decisions in CODE.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict

from ..normalization.price import parse_price_text
from .base import JudgmentKind, JudgmentResult, Question

# ---------- question ids ----------
CLASSIFY_INSTRUMENT = "classify_instrument"
RESTRICTION_RISK = "restriction_risk"
LOOKS_LIKE_BLOCK_PAGE = "looks_like_block_page"
SELECT_FACE_VALUE = "select_face_value"

# Safety questions first: if [enrichment].max_questions_per_offer truncates, the protective ones survive.
QUESTION_PRIORITY = (RESTRICTION_RISK, LOOKS_LIKE_BLOCK_PAGE, CLASSIFY_INSTRUMENT, SELECT_FACE_VALUE)

# ---------- (a) instrument family ----------
# The tracked value-rail families of this project (config/default.toml exit rules: bitsa, paysafecard;
# placeholder/watchlist: crypto_voucher). Other families in config/production.toml (flexepin, neosurf, ...)
# deliberately fall into OTHER: the hint only matters for routing to a family with a sourced exit rule.
OTHER_FAMILY = "other_or_none"
INSTRUMENT_FAMILIES = ("bitsa", "paysafecard", "crypto_voucher")
# observed family aliases -> classifier option (used only to compare the hint with the observed family)
FAMILY_ALIASES = {"bitsa": "bitsa", "paysafecard": "paysafecard", "crypto_voucher": "crypto_voucher",
                  "azteco": "crypto_voucher", "bitnovo": "crypto_voucher"}


def classify_instrument() -> Question:
    return Question(
        id=CLASSIFY_INSTRUMENT, kind=JudgmentKind.CHOICE,
        instructions={
            "question": "Which prepaid instrument family is sold in `offer`?",
            "focus": "Use `offer.title`, `offer.description`, `offer.merchant` and `offer.redemption_program`. "
                     "Judge the product being sold, not the payment method used to buy it.",
        },
        criteria={
            "bitsa": {"what": "Bitsa prepaid card top-up voucher / Bitsa coupon (Pecunia Cards, Bitsa card balance)",
                      "not_for": "paysafecard PINs or crypto vouchers"},
            "paysafecard": {"what": "paysafecard PIN / prepaid code issued by Paysafe",
                            "not_for": "paysafecard Mastercard accounts, Bitsa, crypto vouchers"},
            "crypto_voucher": {"what": "voucher redeemable for cryptocurrency (e.g. Azteco, Bitnovo, Crypto Voucher)",
                               "not_for": "gift cards merely paid for with crypto"},
            OTHER_FAMILY: {"what": "any other gift card / voucher (Flexepin, Neosurf, Steam, Amazon, ...) or "
                                   "not a voucher offer at all"},
        })


# ---------- (b) restriction risk ----------
def restriction_risk() -> Question:
    return Question(
        id=RESTRICTION_RISK, kind=JudgmentKind.NOUL,
        instructions={
            "question": "Does `offer` state or clearly imply that it cannot be redeemed by a customer living in "
                        "`compliant_route.customer_region`, because it is locked to a region outside "
                        "`compliant_route.accepted_regions` or requires an identity/KYC/residency check that such "
                        "a customer cannot complete?",
            "focus": "Only explicit region locks, country restrictions or identity requirements in the offer "
                     "text. Missing information is not a restriction.",
        },
        criteria={
            "true": {"what": "Offer is region-locked away from the customer's region or requires an identity "
                             "check the customer cannot pass",
                     "examples": ["Redeemable in the US only", "Valid for UK accounts only",
                                  "Requires a Turkish ID number to redeem"]},
            "false": {"what": "Offer is usable in the customer's region or says nothing restrictive",
                      "examples": ["EU version", "Region: Germany", "No region information"]},
        })


# ---------- (c) block page detection (detection only - never a bypass) ----------
def looks_like_block_page() -> Question:
    return Question(
        id=LOOKS_LIKE_BLOCK_PAGE, kind=JudgmentKind.NOUL,
        instructions={
            "question": "Is `payload_snippet` a bot-protection, CAPTCHA, access-denied, error or empty page "
                        "instead of real product/offer data?",
        },
        criteria={
            "true": {"what": "Challenge, CAPTCHA, 'Access denied', 'Attention required', rate-limit, error or "
                             "empty placeholder content",
                     "examples": ["Checking your browser before accessing", "403 Forbidden", "Just a moment..."]},
            "false": {"what": "Contains real product or offer data such as names, prices, denominations or "
                              "availability"},
        })


# ---------- (d) face value: select, don't generate ----------
NONE_OPTION = "none_or_uncertain"
_NUM_SPAN = re.compile(
    r"(?:(?:US\$|CA\$|A\$|€|£|\$|EUR|USD|GBP|CHF)\s?)?"
    r"\d{1,6}(?:[.,]\d{3})*(?:[.,]\d{1,2})?"
    r"(?:\s?(?:€|£|\$|EUR|USD|GBP|CHF|Euro|euro))?")


class Candidate(BaseModel):
    """A numeric value extracted BY CODE from the source text. `value` is the only Decimal that may be used."""

    model_config = ConfigDict(frozen=True)

    option_key: str      # "candidate_<n>" - what the model sees and selects
    text: str            # verbatim span
    value: Decimal       # parsed by the project's conservative price parser
    currency: str        # "unknown" unless an unambiguous marker is present ("$" alone stays unknown)
    found_in: str        # state field the span came from
    context: str         # +-30 chars around the span

    def describe(self) -> dict[str, str]:
        return {"text": self.text, "found_in": self.found_in, "context": self.context}

    def evidence(self) -> dict[str, Any]:
        return {"option_key": self.option_key, "text": self.text, "value": str(self.value),
                "currency": self.currency, "found_in": self.found_in}


def extract_numeric_candidates(fields: Iterable[tuple[str, str]], *, limit: int = 20) -> list[Candidate]:
    """Over-find numeric spans in (field_name, text) pairs; dedupe by (value, currency); document order."""
    out: list[Candidate] = []
    seen: set[tuple[Decimal, str]] = set()
    for field, text in fields:
        if not text:
            continue
        for m in _NUM_SPAN.finditer(text):
            span = m.group(0).strip()
            parsed = parse_price_text(span)
            if parsed.amount == "unknown":
                continue
            value = Decimal(parsed.amount)
            if value <= 0:
                continue
            k = (value.normalize(), parsed.currency)
            if k in seen:
                continue
            seen.add(k)
            ctx = text[max(0, m.start() - 30): m.end() + 30].strip()
            out.append(Candidate(option_key=f"candidate_{len(out)}", text=span, value=value,
                                 currency=parsed.currency, found_in=field, context=ctx))
            if len(out) >= limit:
                return out
    return out


def select_face_value(candidates: list[Candidate]) -> Question:
    criteria: dict[str, Any] = {c.option_key: c.describe() for c in candidates}
    criteria[NONE_OPTION] = {"what": "None of the candidates is clearly the face value, or it is ambiguous"}
    return Question(
        id=SELECT_FACE_VALUE, kind=JudgmentKind.CHOICE,
        instructions={
            "question": "Which candidate is the FACE VALUE (nominal amount loaded onto / redeemable from the "
                        "voucher) of the product in `offer`?",
            "not_for": "the selling price, fees, discounts, percentages, quantities, years or SKU numbers",
            "candidates": "Each option describes one number found in the offer text (`text`, where it was "
                          "`found_in`, surrounding `context`).",
        },
        criteria=criteria)


def resolve_selected_candidate(result: JudgmentResult | None, candidates: list[Candidate], *,
                               min_confidence: float) -> Candidate | None:
    """Map the model's option key back to a CODE-extracted candidate. Never parses a number from model output.

    Returns None on abstain, "none/uncertain", an unknown key, low confidence or a non-choice result.
    """
    if result is None or result.abstained or result.kind != JudgmentKind.CHOICE or result.answer is None:
        return None
    if result.answer == NONE_OPTION:
        return None
    by_key = {c.option_key: c for c in candidates}
    cand = by_key.get(result.answer)
    if cand is None:
        return None
    if (result.confidence if result.confidence is not None else 0.0) < min_confidence:
        return None
    return cand
