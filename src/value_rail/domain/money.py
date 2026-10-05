"""Decimal money helpers. Floats are rejected for money on purpose."""

from __future__ import annotations

import decimal
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Literal, Union

from pydantic import BeforeValidator

UNKNOWN: Literal["unknown"] = "unknown"
UnknownT = Literal["unknown"]

MONEY_CONTEXT = decimal.Context(prec=28, rounding=ROUND_HALF_EVEN)


def _reject_float(v: object) -> object:
    if isinstance(v, float):
        raise ValueError("float is not allowed for money/quantity; pass str or Decimal")
    return v


Dec = Annotated[Decimal, BeforeValidator(_reject_float)]
MaybeDecimal = Union[Dec, UnknownT]
MaybeInt = Union[int, UnknownT]


def is_unknown(v: object) -> bool:
    return v is None or v == UNKNOWN


def to_decimal(v: object) -> Decimal:
    if isinstance(v, float):
        raise TypeError("float not allowed for money")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def fmt_eur(v: object, places: int = 2) -> str:
    """German display format: 1.234,56 EUR. 'unknown' stays 'unbekannt'."""
    if is_unknown(v):
        return "unbekannt"
    d = to_decimal(v).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    s = f"{d:,.{places}f}"
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} €"


def fmt_pct(v: object, places: int = 2) -> str:
    if is_unknown(v):
        return "unbekannt"
    d = (to_decimal(v) * 100).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    return f"{d:.{places}f}".replace(".", ",") + " %"
