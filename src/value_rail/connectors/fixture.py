"""Offline fixture connector. Reads SYNTHETIC scenario JSON files; never touches the network.

Fixture timestamps may be relative to the scan clock ("now", "now-90s", "now-2h", "now+10m")
so freshness rules stay deterministic in tests.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..domain.entities import QuantityObservation
from ..domain.enums import EvidenceKind, SourceKind, SourceRole
from ..domain.identity import ProductIdentity
from ..domain.timeutil import resolve_time
from ..evidence import EvidenceDraft
from ..normalization.price import parse_price_text
from ..valuation.models import CheckoutQuoteInput, ExitQuoteInput, FeeComponent
from .base import (Connector, ConnectorCapabilities, DiscoveryItem, NormalizedOffer, QuoteBundle, RawOffer,
                   SourceSpec, SourceUnavailable)


def _qty(d: dict[str, Any] | None, now: datetime) -> QuantityObservation:
    if not d:
        return QuantityObservation()
    at = d.get("observed_at", "unknown")
    return QuantityObservation(value=d.get("value", "unknown"),
                               observed_at=at if at == "unknown" else resolve_time(at, now),
                               scope=d.get("scope", "unknown"))


def _fees(items: list[dict[str, Any]] | None) -> list[FeeComponent]:
    return [FeeComponent.model_validate(f) for f in (items or [])]


def _dec(v: Any) -> Any:
    return "unknown" if v in (None, "unknown") else Decimal(str(v))


class FixtureConnector(Connector):
    key = "fixture"

    def __init__(self, fixtures_dir: str | Path, *, down_sources: set[str] | None = None,
                 scenario_glob: str = "scenarios/*.json", only: set[str] | None = None) -> None:
        self.dir = Path(fixtures_dir)
        self.down_sources = set(down_sources or ())
        self.scenario_glob = scenario_glob
        self.only = only
        self._scenarios: dict[str, dict[str, Any]] = {}

    # ---- interface ----
    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(discovery=True, offer_fetch=True, normalize=True, checkout_quote=True,
                                     exit_quote=True, live_network=False, synthetic=True,
                                     notes="SYNTHETIC offline fixtures; no network access")

    def load(self) -> dict[str, dict[str, Any]]:
        if not self._scenarios:
            for p in sorted(self.dir.glob(self.scenario_glob)):
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("synthetic") is not True:
                    raise ValueError(f"{p}: fixture must be explicitly marked \"synthetic\": true")
                if self.only and data["scenario_id"] not in self.only:
                    continue
                self._scenarios[data["scenario_id"]] = data
        return self._scenarios

    def discovery(self, now: datetime) -> list[DiscoveryItem]:
        items = []
        for sid, sc in self.load().items():
            items.append(DiscoveryItem(
                route_key=f"synthetic:{sid}", product=ProductIdentity.model_validate(sc["product"]),
                product_family=sc.get("product_family", "unknown"),
                sources=[SourceSpec(key=s["key"], name=s["name"], kind=SourceKind(s["kind"]), role=SourceRole(s["role"]))
                         for s in sc["sources"]],
                prerequisites=list(sc.get("prerequisites", [])), is_synthetic=True,
                meta={"scenario_id": sid, "title_de": sc.get("title_de", sid),
                      "regression_case": sc.get("regression_case")}))
        return items

    def _scenario(self, item: DiscoveryItem) -> dict[str, Any]:
        return self.load()[item.meta["scenario_id"]]

    def _check_up(self, source_key: str) -> None:
        if source_key in self.down_sources:
            raise SourceUnavailable(source_key, "SYNTHETIC simulated outage (fixture)")

    def offer_fetch(self, item: DiscoveryItem, now: datetime) -> list[RawOffer]:
        out = []
        for o in self._scenario(item).get("offers", []):
            self._check_up(o["source"])
            out.append(RawOffer(source_key=o["source"], payload=o, fetched_at=now))
        return out

    def _source(self, item: DiscoveryItem, key: str) -> SourceSpec:
        for s in item.sources:
            if s.key == key:
                return s
        raise KeyError(f"fixture references undeclared source {key!r}")

    def _identity(self, item: DiscoveryItem, overrides: dict[str, Any] | None) -> ProductIdentity:
        return ProductIdentity.model_validate(item.product.model_dump() | (overrides or {}))

    def normalize(self, item: DiscoveryItem, raw: RawOffer, now: datetime) -> NormalizedOffer:
        o = raw.payload
        src = self._source(item, raw.source_key)
        if "price_text" in o:
            parsed = parse_price_text(o["price_text"])
            unit_price, currency, text = parsed.amount, parsed.currency, parsed.raw
        else:
            unit_price, currency, text = _dec(o.get("unit_price")), o.get("currency", "unknown"), "unknown"
        captured = resolve_time(o.get("captured_at", "now"), now)
        purchased = _qty(o.get("purchased_quantity"), now)
        ev = [EvidenceDraft(kind=EvidenceKind.LISTING_SNAPSHOT, source_key=src.key, captured_at=captured,
                            scope="listing", summary=f"SYNTHETIC Listing-Snapshot {src.name}: {o.get('price_text', unit_price)}",
                            payload={"fixture": item.meta["scenario_id"], "offer": o}, is_synthetic=True)]
        if purchased.value != "unknown":
            ev.append(EvidenceDraft(kind=EvidenceKind.PURCHASE_RECEIPT, source_key=src.key,
                                    captured_at=purchased.observed_at if purchased.observed_at != "unknown" else captured,
                                    scope=purchased.scope, summary=f"SYNTHETIC historischer Kauf: {purchased.value} Stueck",
                                    payload={"fixture": item.meta["scenario_id"], "purchased_quantity": purchased.value},
                                    is_synthetic=True))
        return NormalizedOffer(
            source=src, identity=self._identity(item, o.get("identity_overrides")), unit_price=unit_price,
            currency=currency, price_text_raw=text, price_includes_fees=bool(o.get("price_includes_fees", False)),
            fees=_fees(o.get("fees")), advertised_quantity=_qty(o.get("advertised_quantity"), now),
            checkout_confirmed_quantity=_qty(o.get("checkout_confirmed_quantity"), now), purchased_quantity=purchased,
            captured_at=captured, evidence=ev, raw=o, is_synthetic=True)

    def checkout_quote(self, item: DiscoveryItem, now: datetime) -> QuoteBundle | None:
        q = self._scenario(item).get("checkout_quote")
        if not q:
            return None
        self._check_up(q["source"])
        src = self._source(item, q["source"])
        captured = resolve_time(q.get("captured_at", "now"), now)
        vu = q.get("valid_until", "unknown")
        quote = CheckoutQuoteInput(
            quote_ref="pending", source_key=src.key, identity=self._identity(item, q.get("identity_overrides")),
            unit_price=_dec(q.get("unit_price")), currency=q.get("currency", "unknown"),
            quantity_confirmed=q.get("quantity_confirmed", "unknown"), fees=_fees(q.get("fees")),
            captured_at=captured, valid_until=vu if vu == "unknown" else resolve_time(vu, now))
        ev = [EvidenceDraft(kind=EvidenceKind.CHECKOUT_QUOTE, source_key=src.key, captured_at=captured,
                            scope="checkout_session", summary=f"SYNTHETIC Checkout-Quote {src.name}",
                            payload={"fixture": item.meta["scenario_id"], "quote": q}, is_synthetic=True)]
        return QuoteBundle(source=src, quote=quote, evidence=ev)

    def exit_quote(self, item: DiscoveryItem, now: datetime) -> QuoteBundle | None:
        q = self._scenario(item).get("exit_quote")
        if not q:
            return None
        self._check_up(q["venue"])
        src = self._source(item, q["venue"])
        captured = resolve_time(q.get("captured_at", "now"), now)
        vu = q.get("valid_until", "unknown")
        quote = ExitQuoteInput(
            quote_ref="pending", venue_key=src.key, identity=self._identity(item, q.get("identity_overrides")),
            unit_price=_dec(q.get("unit_price")), currency=q.get("currency", "unknown"),
            depth_quantity=q.get("depth_quantity", "unknown"), fees=_fees(q.get("fees")),
            captured_at=captured, valid_until=vu if vu == "unknown" else resolve_time(vu, now))
        ev = [EvidenceDraft(kind=EvidenceKind.EXIT_QUOTE, source_key=src.key, captured_at=captured, scope="exit_quote",
                            summary=f"SYNTHETIC Exit-Quote {src.name}",
                            payload={"fixture": item.meta["scenario_id"], "quote": q}, is_synthetic=True)]
        return QuoteBundle(source=src, quote=quote, evidence=ev)


def load_operator_profiles(fixtures_dir: str | Path) -> list[dict[str, Any]]:
    p = Path(fixtures_dir) / "operator_profiles.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("synthetic") is not True:
        raise ValueError("operator_profiles.json must be marked synthetic")
    return data["profiles"]
