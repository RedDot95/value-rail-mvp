"""Price text parsing. Conservative: ambiguous symbols yield currency 'unknown'.

"$100" -> amount 100, currency "unknown" (could be USD, CAD, AUD, ... - never assumed USD).
"US$100", "100 USD" -> USD. "€", "EUR" -> EUR. "£", "GBP" -> GBP.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from ..domain.money import MaybeDecimal

_UNAMBIGUOUS = {
    "€": "EUR", "EUR": "EUR", "EURO": "EUR",
    "US$": "USD", "USD": "USD",
    "£": "GBP", "GBP": "GBP",
    "CHF": "CHF",
    "CA$": "CAD", "CAD": "CAD",
    "A$": "AUD", "AUD": "AUD",
}
_AMBIGUOUS = {"$", "¥", "KR", "KR."}

_TOKEN = re.compile(r"(US\$|CA\$|A\$|[A-Za-z]{3,4}\.?|[€$£¥])")
_NUMBER = re.compile(r"\d[\d.,\s]*")


class ParsedPrice(BaseModel):
    amount: MaybeDecimal
    currency: str
    raw: str
    note: str = ""


def _parse_number(s: str) -> Decimal:
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:
        # the right-most separator is the decimal separator
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = (head.replace(",", "") + "." + tail) if len(tail) != 3 else s.replace(",", "")
    return Decimal(s)


def parse_price_text(raw: str) -> ParsedPrice:
    text = (raw or "").strip()
    num = _NUMBER.search(text)
    amount: MaybeDecimal = "unknown"
    if num:
        try:
            amount = _parse_number(num.group(0))
        except InvalidOperation:
            amount = "unknown"
    currency = "unknown"
    note = ""
    for tok in _TOKEN.findall(text):
        t = tok.upper()
        if t in _UNAMBIGUOUS:
            currency = _UNAMBIGUOUS[t]
            break
        if t in _AMBIGUOUS:
            note = f"ambiguous currency symbol {tok!r}; currency left unknown"
    if currency == "unknown" and not note:
        note = "no currency marker found; currency left unknown"
    return ParsedPrice(amount=amount, currency=currency, raw=text, note=note if currency == "unknown" else "")
