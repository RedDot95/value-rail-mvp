"""Abstract connector interface.

Every connector self-reports capabilities. A capability may only be reported True when the
connector actually implements it against a verified source. Nothing here ever buys anything.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..domain.entities import QuantityObservation
from ..domain.enums import SourceKind, SourceRole
from ..domain.identity import ProductIdentity
from ..evidence import EvidenceDraft
from ..valuation.models import CheckoutQuoteInput, ExitQuoteInput, FeeComponent, Prerequisite


class SourceUnavailable(RuntimeError):
    """Source could not be reached/parsed. This is a DISTURBANCE, never 'no deals'."""

    def __init__(self, source_key: str, message: str) -> None:
        super().__init__(f"{source_key}: {message}")
        self.source_key = source_key


class CapabilityNotSupported(NotImplementedError):
    pass


class ConnectorCapabilities(BaseModel):
    discovery: bool = False
    offer_fetch: bool = False
    normalize: bool = False
    checkout_quote: bool = False
    exit_quote: bool = False
    live_network: bool = False  # Delivery 1: always False
    synthetic: bool = False
    notes: str = ""


class SourceSpec(BaseModel):
    key: str
    name: str
    kind: SourceKind
    role: SourceRole


class DiscoveryItem(BaseModel):
    """A route candidate: product reference + the sources that describe it."""

    route_key: str
    product: ProductIdentity
    product_family: str = "unknown"
    sources: list[SourceSpec]
    prerequisites: list[str] = Field(default_factory=list)  # operator capability names
    is_synthetic: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


class RawOffer(BaseModel):
    source_key: str
    payload: dict[str, Any]
    fetched_at: datetime


class NormalizedOffer(BaseModel):
    source: SourceSpec
    identity: ProductIdentity
    unit_price: Any  # Decimal | "unknown"
    currency: str
    price_text_raw: str
    price_includes_fees: bool
    fees: list[FeeComponent]
    advertised_quantity: QuantityObservation
    checkout_confirmed_quantity: QuantityObservation
    purchased_quantity: QuantityObservation
    captured_at: datetime
    evidence: list[EvidenceDraft] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    is_synthetic: bool = False


class QuoteBundle(BaseModel):
    """Connector output for optional quote capabilities (refs are assigned by storage)."""

    source: SourceSpec
    quote: CheckoutQuoteInput | ExitQuoteInput
    evidence: list[EvidenceDraft] = Field(default_factory=list)


class Connector(ABC):
    key: str

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities: ...

    @abstractmethod
    def discovery(self, now: datetime) -> list[DiscoveryItem]: ...

    @abstractmethod
    def offer_fetch(self, item: DiscoveryItem, now: datetime) -> list[RawOffer]: ...

    @abstractmethod
    def normalize(self, item: DiscoveryItem, raw: RawOffer, now: datetime) -> NormalizedOffer: ...

    def checkout_quote(self, item: DiscoveryItem, now: datetime) -> QuoteBundle | None:
        raise CapabilityNotSupported(f"{self.key}: checkout_quote not supported")

    def exit_quote(self, item: DiscoveryItem, now: datetime) -> QuoteBundle | None:
        raise CapabilityNotSupported(f"{self.key}: exit_quote not supported")

    def prerequisites(self, item: DiscoveryItem, operator_caps: dict[str, str]) -> list[Prerequisite]:
        return [Prerequisite(name=n, status=operator_caps.get(n, "unknown")) for n in item.prerequisites]
