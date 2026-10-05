"""Product and asset identity rules.

Product identity = face value + currency + region + variant + seller + redemption program.
Two offers only describe the same product if ALL identity fields match exactly.
Asset identity = chain + contract address. A matching ticker alone NEVER merges assets.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from .money import Dec, UnknownT


class ProductIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    face_value: Dec | UnknownT
    face_currency: str  # ISO-4217 or "unknown"
    region: str
    variant: str
    seller: str
    redemption_program: str

    @field_validator("face_currency", "region", "variant", "seller", "redemption_program")
    @classmethod
    def _norm(cls, v: str) -> str:
        v = (v or "").strip()
        return v if v else "unknown"

    def key(self) -> str:
        fv = self.face_value if self.face_value == "unknown" else format(Decimal(self.face_value).normalize(), "f")
        parts = [str(fv), self.face_currency.upper(), self.region.lower(), self.variant.lower(),
                 self.seller.lower(), self.redemption_program.lower()]
        return "|".join(parts)

    def key_hash(self) -> str:
        return hashlib.sha256(self.key().encode()).hexdigest()[:16]

    def mismatches(self, other: "ProductIdentity") -> list[str]:
        """Return identity fields that differ (empty list = identical product)."""
        a, b = self.key().split("|"), other.key().split("|")
        names = ["face_value", "face_currency", "region", "variant", "seller", "redemption_program"]
        out = [n for n, x, y in zip(names, a, b) if x != y]
        # "unknown" never matches anything (cannot prove identity)
        for n, x in zip(names, a):
            if x == "unknown" and n not in out:
                out.append(n)
        return out


class AssetIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    chain: str
    contract_address: str

    def key(self) -> str:
        return f"{self.chain.strip().lower()}:{self.contract_address.strip().lower()}"


def can_merge_assets(a: AssetIdentity, b: AssetIdentity) -> bool:
    """Same ticker is irrelevant; chain AND contract must match and be known."""
    if "unknown" in (a.chain, a.contract_address, b.chain, b.contract_address):
        return False
    return a.key() == b.key()
