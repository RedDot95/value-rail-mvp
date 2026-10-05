"""Placeholders for the Bitsa and Paysafe product families (Bauauftrag candidates).

Deliberately NOT implemented: no endpoints, selectors or checkout flows are known/verified.
All capabilities are reported False. See docs/sources.md for what Delivery 2 needs.
"""

from __future__ import annotations

from datetime import datetime

from .base import Connector, ConnectorCapabilities, DiscoveryItem, NormalizedOffer, RawOffer


class PlaceholderConnector(Connector):
    def __init__(self, key: str, product_family: str, notes: str = "") -> None:
        self.key = key
        self.product_family = product_family
        self.notes = notes or "geplant - kein verifizierter Zugang"

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(notes=f"PLACEHOLDER ({self.product_family}): {self.notes}")

    def _nope(self):
        raise NotImplementedError(f"{self.key}: placeholder connector - planned for Delivery 2, no live access")

    def discovery(self, now: datetime) -> list[DiscoveryItem]:
        self._nope()

    def offer_fetch(self, item: DiscoveryItem, now: datetime) -> list[RawOffer]:
        self._nope()

    def normalize(self, item: DiscoveryItem, raw: RawOffer, now: datetime) -> NormalizedOffer:
        self._nope()


def bitsa_placeholder() -> PlaceholderConnector:
    return PlaceholderConnector("bitsa", "bitsa", "Kandidat; Zugang/ToS/Checkout-Nachweis offen")


def paysafe_placeholder() -> PlaceholderConnector:
    return PlaceholderConnector("paysafe", "paysafecard", "Kandidat; Zugang/ToS/Checkout-Nachweis offen")
