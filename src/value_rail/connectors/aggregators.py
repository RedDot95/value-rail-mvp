"""Discovery-only aggregator / comparison-site connectors (Delivery 06.10.2026).

Every connector in this module is HARD-WIRED to `SourceKind.AGGREGATOR` + `SourceRole.DISCOVERY_ONLY`.
There is no config switch to change that. Consequences (enforced by the valuation engine, not by us):
- an aggregator offer is never a price basis -> a route that only has aggregator offers is always
  `blocked` with `direct_price_unverified:only_discovery_only_offers`; it can never become a Preisfund,
  a verified route or an alert. Aggregator prices are HINTS; the direct seller price must be re-verified
  with a price_basis connector first.
- additionally every lead carries a REQUIRED fee with amount "unknown" (no checkout quote, never opened).

Sources (access basis + date in docs/sources.md):
- `coingate_mcp`  CoinGate Gift Cards - official, documented, no-auth MCP server
                  (https://giftcards-api.coingate.com/api/mcp, Streamable HTTP, JSON-RPC). Only the read-only
                  tools search_gift_cards / get_gift_card / list_categories are callable; quote_order,
                  create_order, get_order, notify_when_in_stock, list_payment_methods are refused client-side.
                  No email is ever sent. CoinGate is itself the seller (UAB Rewards Distributed).
- `bsv_list`      BuySellVouchers category listing pages /en/products/list/<category>/ (robots allows paths
                  without query; Next.js RSC payload `initialProductsList` in the plain HTML response).
                  Seller = public store name; individual sellers without store name are pseudonymised.
- `cardbear_html` CardBear brand comparison pages /gift-card-discount/<id>/<slug> (server-rendered table,
                  discount % per marketplace; the /r.php outbound link is robots-disallowed and NEVER followed,
                  only recorded). US market, no prices -> unit price "unknown".
- `gcw_hotdeals`  GiftCardWiki /hot-deals/ brand summary (server-rendered: brand, % off, card count).
                  US market, no prices, no underlying seller in the HTML.

Common rules: SafeHttpClient (https only, host allowlist, public-IP pinning, redirect re-validation,
robots.txt RFC 9309, >= 5 s/host + jitter, 429/403/401 distinct), configured targets only (no crawling,
no search pages, no sitemap walking, no internal/undocumented APIs), never cart/checkout/account/login,
no cookies, no UA spoofing. A parser that cannot find its anchor raises ParserBroken; a listing that
unexpectedly has no rows raises UnexpectedEmpty - neither is ever reported as "zero offers".
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..domain.entities import QuantityObservation
from ..domain.enums import EvidenceKind, SourceKind, SourceRole
from ..domain.identity import ProductIdentity
from ..evidence import EvidenceDraft
from ..net.errors import ParserBroken, UnexpectedEmpty, UpstreamError
from ..net.http_safe import PolitenessPolicy, SafeHttpClient
from ..valuation.models import FeeComponent
from .base import (Connector, ConnectorCapabilities, DiscoveryItem, NormalizedOffer, RawOffer, SourceSpec,
                   SourceUnavailable)
from .jsonld_shop import slugify

AGG_FEE_NOTE = ("Aggregator-Hinweis: kein Kaufpreisnachweis, Gebuehren/Checkout unbekannt - Direktpreis beim "
                "Verkaeufer muss separat verifiziert werden")


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def pseudonym(prefix: str, value: str) -> str:
    """Stable, non-reversible label for an individual (non-store) seller."""
    return f"{prefix}-{hashlib.sha256(value.encode()).hexdigest()[:8]}"


_FACE_PATTERNS = [
    re.compile(r"(?<![\d.,])(\d{1,5}(?:[.,]\d{1,2})?)\s*(EUR|USD|GBP|€|\$|£)(?![a-z])", re.I),
    re.compile(r"(EUR|USD|GBP|€|\$|£)\s*(\d{1,5}(?:[.,]\d{1,2})?)(?![\d])", re.I),
]
_SYM = {"€": "EUR", "$": "USD", "£": "GBP"}


def face_from_title(title: str) -> tuple[Decimal | str, str]:
    """'Bitsa Euro Area - 100 EUR' -> (100, 'EUR'); 'Azteco ... USD100' -> (100, 'USD'); else unknown."""
    for i, rx in enumerate(_FACE_PATTERNS):
        m = rx.search(title or "")
        if m:
            num, cur = (m.group(1), m.group(2)) if i == 0 else (m.group(2), m.group(1))
            d = _dec(num)
            if d is not None and d > 0:
                return d, _SYM.get(cur, cur.upper())
    return "unknown", "unknown"


# --------------------------------------------------------------------------------------------- models
@dataclass
class AggLead:
    lead_id: str                         # stable within the target
    title: str
    seller: str                          # underlying seller / marketplace as named by the aggregator
    face_value: Decimal | str = "unknown"
    face_currency: str = "unknown"
    price: str | None = None             # as published (string) - None = aggregator shows no price
    currency: str = "unknown"
    discount_percent: str | None = None  # as published by the aggregator (not recomputed)
    quantity: int | str = "unknown"
    availability: str = "unknown"        # InStock | OutOfStock | unknown
    region: str = "unknown"
    seller_link: str | None = None       # recorded only, NEVER followed
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AggPage:
    target_id: str
    url: str
    http_status: int
    leads: list[AggLead]
    body_sha256: str
    body_bytes: int
    data_sha256: str
    notes: list[str] = field(default_factory=list)


class AggTarget(BaseModel):
    """One configured page / API call. `family`, `redemption_program`, `region` describe the leads."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    family: str = "unknown"
    redemption_program: str = "unknown"
    region: str = "unknown"
    tier: str = "discover"
    empty_ok: bool = False  # an explicit, schema-valid empty answer is a real observation (e.g. clearance list)
    prerequisites: list[str] = Field(default_factory=list)
    note: str = ""


class AggregatorConfigBase(BaseModel):
    # extra="forbid": there is deliberately no `role`/`source_kind` option - aggregators are always discovery_only
    model_config = ConfigDict(extra="forbid")

    source_key: str
    source_name: str
    host: str
    min_interval_s: float = 6.0
    jitter_s: float = 2.0
    max_retries: int = 1

    @field_validator("min_interval_s")
    @classmethod
    def _polite(cls, v: float) -> float:
        if v < 5:
            raise ValueError("min_interval_s must be >= 5 (project politeness rule)")
        return v


# --------------------------------------------------------------------------------------------- base
class AggregatorConnector(Connector):
    """Shared discovery/offer_fetch/normalize for all aggregator parsers (role fixed: discovery_only)."""

    PARSER_NAME = "aggregator"
    PARSER_VERSION = "aggregator/0"
    ROLE = SourceRole.DISCOVERY_ONLY
    KIND = SourceKind.AGGREGATOR

    def __init__(self, config: AggregatorConfigBase, *, client: SafeHttpClient | None = None) -> None:
        self.config = config
        self.key = config.source_key
        self.source = SourceSpec(key=config.source_key, name=config.source_name, kind=self.KIND, role=self.ROLE)
        self.client = client or SafeHttpClient(
            source_key=config.source_key, allowed_hosts={config.host},
            policy=PolitenessPolicy(min_interval_s=config.min_interval_s, jitter_s=config.jitter_s,
                                    max_retries=config.max_retries))
        self.active_tiers: set[str] | None = None
        self._pages: dict[str, tuple[AggPage, datetime]] = {}
        self._errors: dict[str, SourceUnavailable] = {}
        self.ok_pages: set[str] = set()

    # ---- to implement ----
    @abstractmethod
    def targets(self) -> list[AggTarget]: ...

    @abstractmethod
    def fetch_target(self, t: AggTarget) -> AggPage: ...

    @abstractmethod
    def describe(self) -> str: ...

    # ---- shared ----
    def configure_for_job(self, options: dict[str, Any]) -> None:
        tiers = options.get("tiers")
        self.active_tiers = set(tiers) if tiers else None

    def selected_targets(self) -> list[AggTarget]:
        return [t for t in self.targets() if self.active_tiers is None or t.tier in self.active_tiers]

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            discovery=True, offer_fetch=True, normalize=True, checkout_quote=False, exit_quote=False,
            live_network=True, synthetic=False,
            notes=(f"{self.config.source_name}: {self.describe()}; role discovery_only (Aggregator - nur Hinweise, "
                   f"nie Preisbasis, nie Alert); kein Checkout/Warenkorb/Konto; robots.txt + >=5 s/Host + Jitter; "
                   f"parser {self.PARSER_VERSION}"))

    def _html_get(self, url: str):
        res = self.client.get(url)
        key = self.config.source_key
        if res.status == 404:
            raise UpstreamError(key, f"page {url} returned 404 (removed/renamed?)", url=url, http_status=404)
        if not 200 <= res.status < 300:
            raise UpstreamError(key, f"unexpected HTTP {res.status} for {url}", url=url, http_status=res.status)
        if "html" not in res.content_type.lower():
            raise ParserBroken(key, f"unexpected content-type {res.content_type!r} for {url}", url=url,
                               http_status=res.status)
        return res

    def discovery(self, now: datetime) -> list[DiscoveryItem]:
        items: list[DiscoveryItem] = []
        self._pages.clear()
        self._errors.clear()
        self.ok_pages = set()
        key = self.config.source_key
        for t in self.selected_targets():
            try:
                page = self.fetch_target(t)
            except SourceUnavailable as exc:
                self._errors[t.id] = exc
                items.append(DiscoveryItem(
                    route_key=f"{key}:{t.id}:page",
                    product=ProductIdentity(face_value="unknown", face_currency="unknown", region=t.region,
                                            variant="unknown", seller="unknown",
                                            redemption_program=t.redemption_program),
                    product_family=t.family, sources=[self.source], prerequisites=list(t.prerequisites),
                    meta={"target_id": t.id, "page_error": True}))
                continue
            self._pages[t.id] = (page, now)
            self.ok_pages.add(page.url)
            for ld in page.leads:
                ident = ProductIdentity(
                    face_value=ld.face_value, face_currency=ld.face_currency if ld.face_value != "unknown" else "unknown",
                    region=ld.region if ld.region != "unknown" else t.region, variant=f"aggregator-lead:{ld.lead_id}",
                    seller=ld.seller, redemption_program=t.redemption_program)
                items.append(DiscoveryItem(
                    route_key=f"{key}:{t.id}:{slugify(ld.lead_id)}", product=ident, product_family=t.family,
                    sources=[self.source], prerequisites=list(t.prerequisites),
                    meta={"target_id": t.id, "lead_id": ld.lead_id, "title": ld.title,
                          "tier": t.tier, "discovery_only": True}))
        return items

    def offer_fetch(self, item: DiscoveryItem, now: datetime) -> list[RawOffer]:
        tid = item.meta.get("target_id")
        if item.meta.get("page_error"):
            raise self._errors[tid]
        if tid not in self._pages:
            t = next(x for x in self.targets() if x.id == tid)
            self._pages[tid] = (self.fetch_target(t), now)
        page, fetched_at = self._pages[tid]
        ld = next((x for x in page.leads if x.lead_id == item.meta.get("lead_id")), None)
        if ld is None:
            raise UnexpectedEmpty(self.config.source_key, f"lead {item.meta.get('lead_id')} vanished from {page.url}",
                                  url=page.url)
        return [RawOffer(source_key=self.config.source_key, fetched_at=fetched_at, payload={
            "page_url": page.url, "http_status": page.http_status, "body_sha256": page.body_sha256,
            "body_bytes": page.body_bytes, "data_sha256": page.data_sha256, "notes": page.notes,
            "lead": {"lead_id": ld.lead_id, "title": ld.title, "seller": ld.seller, "price": ld.price,
                     "currency": ld.currency, "discount_percent": ld.discount_percent, "quantity": ld.quantity,
                     "availability": ld.availability, "region": ld.region, "seller_link": ld.seller_link,
                     "face_value": str(ld.face_value), "face_currency": ld.face_currency, "raw": ld.raw},
            "tier": item.meta.get("tier")})]

    def normalize(self, item: DiscoveryItem, raw: RawOffer, now: datetime) -> NormalizedOffer:
        c = self.config
        pl = raw.payload
        ld = pl["lead"]
        price = _dec(ld["price"]) if ld["price"] is not None else None
        if ld["availability"] == "OutOfStock":
            adv = QuantityObservation(value=0, observed_at=raw.fetched_at, scope="aggregator listing: out of stock")
        elif isinstance(ld["quantity"], int):
            adv = QuantityObservation(value=ld["quantity"], observed_at=raw.fetched_at,
                                      scope="aggregator listing: published stock (hint only)")
        else:
            adv = QuantityObservation(value="unknown", observed_at=raw.fetched_at,
                                      scope=f"aggregator listing: {ld['availability']} (no unit count)")
        fee = FeeComponent(name=f"{slugify(c.source_key)}_checkout_fees", kind="fixed_per_order", amount="unknown",
                           required=True, evidence_ref="unknown", note=AGG_FEE_NOTE)
        price_txt = f"{ld['price']} {ld['currency']}" if ld["price"] is not None else "kein Preis publiziert"
        disc_txt = f", Rabatt laut Aggregator {ld['discount_percent']} %" if ld["discount_percent"] is not None else ""
        seller_offer = {"source_key": c.source_key, "page_url": pl["page_url"], "seller": ld["seller"],
                        "sku": ld["lead_id"], "offer_key": f"{slugify(ld['seller'])}|{ld['lead_id']}",
                        "price": ld["price"] if ld["price"] is not None else "unknown",
                        "currency": ld["currency"], "quantity": ld["quantity"], "region": item.product.region,
                        "availability": ld["availability"]}
        evidence = [EvidenceDraft(
            kind=EvidenceKind.LISTING_SNAPSHOT, source_key=c.source_key, captured_at=raw.fetched_at,
            scope="aggregator_lead:discovery_only",
            summary=(f"[nur Discovery] {ld['title']} - Verkaeufer laut Aggregator: {ld['seller']}: {price_txt}"
                     f"{disc_txt} ({ld['availability']})"),
            payload={"url": pl["page_url"], "http_status": pl["http_status"], "parser": self.PARSER_NAME,
                     "parser_version": self.PARSER_VERSION, "data_sha256": pl["data_sha256"],
                     "body_sha256": pl["body_sha256"], "body_bytes": pl["body_bytes"], "lead": ld,
                     "robots_txt_checked": self.client.respect_robots, "source_role": self.ROLE.value,
                     "source_kind": self.KIND.value, "fetched_at_utc": raw.fetched_at.isoformat(),
                     "notes": pl["notes"]})]
        return NormalizedOffer(
            source=self.source, identity=item.product, unit_price=price if price is not None else "unknown",
            currency=ld["currency"] if price is not None else (ld["currency"] or "unknown"),
            price_text_raw=price_txt, price_includes_fees=False, fees=[fee], advertised_quantity=adv,
            checkout_confirmed_quantity=QuantityObservation(), purchased_quantity=QuantityObservation(),
            captured_at=raw.fetched_at, evidence=evidence,
            raw={"lead_id": ld["lead_id"], "seller": ld["seller"], "seller_link": ld["seller_link"],
                 "discount_percent": ld["discount_percent"], "availability": ld["availability"],
                 "parser_version": self.PARSER_VERSION, "page_url": pl["page_url"], "source_role": self.ROLE.value,
                 "discovery_only": True, "seller_offer": seller_offer},
            is_synthetic=False)


# ============================================================================== CoinGate (official MCP)
COINGATE_SELLER = "CoinGate Gift Cards (UAB Rewards Distributed)"
MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_READ_ONLY_TOOLS = frozenset({"search_gift_cards", "get_gift_card", "list_categories"})


class CoinGateBrand(AggTarget):
    brand: str
    country: str  # ISO alpha-2 or WW


class CoinGateSearch(AggTarget):
    category: str
    country: str
    per_page: int = Field(default=25, ge=1, le=25)


class CoinGateMcpConfig(AggregatorConfigBase):
    host: str = "giftcards-api.coingate.com"
    endpoint_path: str = "/api/mcp"
    brands: list[CoinGateBrand] = Field(default_factory=list)
    searches: list[CoinGateSearch] = Field(default_factory=list)


def _mcp_decode(body: bytes, content_type: str, want_id: int, key: str, url: str) -> dict:
    """Decode a Streamable-HTTP answer: plain JSON or an SSE stream (last `data:` with our id)."""
    text = body.decode("utf-8", errors="replace")
    msgs: list[Any] = []
    if "text/event-stream" in content_type.lower():
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    msgs.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    continue
    else:
        try:
            msgs.append(json.loads(text))
        except json.JSONDecodeError:
            raise ParserBroken(key, f"MCP answer is not JSON ({content_type!r})", url=url) from None
    for m in reversed(msgs):
        if isinstance(m, dict) and m.get("id") == want_id:
            return m
    raise ParserBroken(key, f"no JSON-RPC response with id {want_id} in MCP answer", url=url)


def _mcp_payload(msg: dict, key: str, url: str, tool: str) -> dict:
    if "error" in msg:
        err = msg["error"] if isinstance(msg["error"], dict) else {"message": str(msg["error"])}
        raise UpstreamError(key, f"MCP JSON-RPC error for {tool}: {err.get('code')} {err.get('message')}", url=url)
    res = msg.get("result")
    if not isinstance(res, dict):
        raise ParserBroken(key, f"MCP result for {tool} missing", url=url)
    if res.get("isError"):
        txt = " ".join(str(c.get("text", ""))[:200] for c in res.get("content", []) if isinstance(c, dict))
        raise UpstreamError(key, f"MCP tool {tool} returned isError: {txt}", url=url)
    sc = res.get("structuredContent")
    if isinstance(sc, dict):
        return sc
    for c in res.get("content", []):
        if isinstance(c, dict) and c.get("type") == "text":
            try:
                d = json.loads(c.get("text", ""))
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict):
                return d
    raise ParserBroken(key, f"MCP tool {tool}: neither structuredContent nor JSON text content", url=url)


def parse_coingate_gift_card(key: str, t: CoinGateBrand, url: str, sc: dict) -> list[AggLead]:
    products = sc.get("products")
    brand = sc.get("brand") if isinstance(sc.get("brand"), dict) else {}
    if not isinstance(products, list):
        raise ParserBroken(key, f"get_gift_card({t.brand},{t.country}): no products[] (schema change?)", url=url)
    link = brand.get("url") if isinstance(brand.get("url"), str) else None
    leads: list[AggLead] = []
    for p in products:
        if not isinstance(p, dict) or "gift_card_id" not in p:
            raise ParserBroken(key, f"get_gift_card({t.brand}): product without gift_card_id", url=url)
        gid, cur = p["gift_card_id"], str(p.get("currency") or "unknown").upper()
        region = str(p.get("region") or t.country)
        in_stock = p.get("in_stock")
        avail = "InStock" if in_stock is True else ("OutOfStock" if in_stock is False else "unknown")
        qty = p["stock_count"] if isinstance(p.get("stock_count"), int) else "unknown"
        base = {"gift_card_id": gid, "name": p.get("name"), "region": region, "currency": cur,
                "in_stock": in_stock, "stock_count": p.get("stock_count"), "delivery": p.get("delivery")}
        for d in p.get("denominations") or []:
            v, pr = _dec(d.get("value")), _dec(d.get("price"))
            if v is None or pr is None:
                raise ParserBroken(key, f"get_gift_card({t.brand}): denomination without value/price", url=url)
            disc = format(((Decimal(1) - pr / v) * 100).quantize(Decimal("0.01")), "f") if v > 0 else None
            leads.append(AggLead(
                lead_id=f"{gid}-{format(v.normalize(), 'f')}", title=f"{p.get('name')} {d.get('label') or v}",
                seller=COINGATE_SELLER, face_value=v, face_currency=cur, price=str(d.get("price")), currency=cur,
                discount_percent=disc, quantity=qty, availability=avail, region=region, seller_link=link,
                raw=base | {"denomination": d}))
        rng = p.get("amount_range")
        if isinstance(rng, dict) and _dec(rng.get("min")) and _dec(rng.get("price_at_min")) is not None:
            v, pr = _dec(rng["min"]), _dec(rng["price_at_min"])
            leads.append(AggLead(
                lead_id=f"{gid}-range-{format(v.normalize(), 'f')}", title=f"{p.get('name')} (Betrag frei, ab {v} {cur})",
                seller=COINGATE_SELLER, face_value=v, face_currency=cur, price=str(rng["price_at_min"]), currency=cur,
                discount_percent=format(((Decimal(1) - pr / v) * 100).quantize(Decimal("0.01")), "f"),
                quantity=qty, availability=avail, region=region, seller_link=link, raw=base | {"amount_range": rng}))
    for i, o in enumerate(sc.get("clearance_offers") or []):
        if not isinstance(o, dict):
            continue
        v = _dec(o.get("denomination", o.get("value")))
        cur = str(o.get("currency") or "unknown").upper()
        leads.append(AggLead(
            lead_id=f"clearance-{o.get('gift_card_id', i)}-{format(v.normalize(), 'f') if v else i}",
            title=f"CLEARANCE {o.get('name') or brand.get('name') or t.brand}", seller=COINGATE_SELLER,
            face_value=v if v else "unknown", face_currency=cur if v else "unknown",
            price=str(o["price"]) if o.get("price") is not None else None, currency=cur,
            discount_percent=str(o["discount_percent"]) if o.get("discount_percent") is not None else None,
            quantity=o["stock_count"] if isinstance(o.get("stock_count"), int) else "unknown",
            availability="InStock" if o.get("in_stock", True) else "OutOfStock",
            region=str(o.get("region") or t.country), seller_link=link, raw={"clearance_offer": o}))
    if not leads and not t.empty_ok:
        raise UnexpectedEmpty(key, f"get_gift_card({t.brand},{t.country}) returned 0 products", url=url)
    return leads


def parse_coingate_search(key: str, t: CoinGateSearch, url: str, sc: dict) -> tuple[list[AggLead], list[str]]:
    results = sc.get("results")
    if not isinstance(results, list) or "total_results" not in sc:
        raise ParserBroken(key, f"search_gift_cards({t.category},{t.country}): no results[]/total_results", url=url)
    notes = [f"total_results={sc.get('total_results')} total_pages={sc.get('total_pages')} (nur Seite 1 gelesen)"]
    if not results:
        if t.empty_ok and int(sc.get("total_results") or 0) == 0:
            return [], notes + ["API meldet explizit 0 Treffer (gueltiges Schema) - echte Beobachtung, keine Stoerung"]
        raise UnexpectedEmpty(key, f"search_gift_cards({t.category},{t.country}) returned 0 results", url=url)
    leads = []
    for r in results:
        if not isinstance(r, dict) or not r.get("brand_slug"):
            raise ParserBroken(key, "search result without brand_slug", url=url)
        stock = r.get("in_stock_in_country")
        leads.append(AggLead(
            lead_id=f"brand-{r['brand_slug']}", title=f"{r.get('name')} (Marke, max. Rabatt)", seller=COINGATE_SELLER,
            discount_percent=None if r.get("max_discount_percent") is None else str(r["max_discount_percent"]),
            availability="InStock" if stock is True else ("OutOfStock" if stock is False else "unknown"),
            region=t.country, seller_link=r.get("url") if isinstance(r.get("url"), str) else None,
            raw={k: r.get(k) for k in ("brand_slug", "name", "categories", "max_discount_percent",
                                       "available_in_country", "in_stock_in_country", "url")}))
    return leads, notes


class CoinGateMcpConnector(AggregatorConnector):
    PARSER_NAME = "coingate-mcp"
    PARSER_VERSION = "coingate-mcp/1.0.0"
    config: CoinGateMcpConfig

    def __init__(self, config: CoinGateMcpConfig, *, client: SafeHttpClient | None = None) -> None:
        super().__init__(config, client=client)
        self._rpc_id = 0
        self._initialized = False

    @property
    def endpoint(self) -> str:
        return f"https://{self.config.host}{self.config.endpoint_path}"

    def describe(self) -> str:
        return ("offizieller, dokumentierter MCP-Server ohne Login (nur read-only Tools search_gift_cards/"
                "get_gift_card; Bestell-/Quote-Tools werden clientseitig verweigert); CoinGate ist selbst Verkaeufer")

    def targets(self) -> list[AggTarget]:
        out: list[AggTarget] = []
        for b in self.config.brands:
            out.append(b.model_copy(update={"id": b.id or f"card-{slugify(b.brand)}-{b.country.lower()}"}))
        for s in self.config.searches:
            out.append(s.model_copy(update={"id": s.id or f"search-{slugify(s.category)}-{s.country.lower()}"}))
        return out

    def _rpc(self, method: str, params: dict | None) -> dict:
        self._rpc_id += 1
        rid = self._rpc_id
        body = {"jsonrpc": "2.0", "id": rid, "method": method} | ({"params": params} if params is not None else {})
        res = self.client.post_json(self.endpoint, json.dumps(body).encode(), accept="application/json, text/event-stream",
                                    extra_headers={"mcp-protocol-version": MCP_PROTOCOL_VERSION})
        if not 200 <= res.status < 300:
            raise UpstreamError(self.config.source_key, f"MCP HTTP {res.status}", url=self.endpoint,
                                http_status=res.status)
        msg = _mcp_decode(res.body, res.content_type, rid, self.config.source_key, self.endpoint)
        msg["_body_sha256"], msg["_body_bytes"], msg["_status"] = _sha(res.body), len(res.body), res.status
        return msg

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        msg = self._rpc("initialize", {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {},
                                       "clientInfo": {"name": "value-rail-mvp", "version": "0.3"}})
        if "error" in msg or not isinstance(msg.get("result"), dict):
            raise UpstreamError(self.config.source_key, f"MCP initialize failed: {msg.get('error')}", url=self.endpoint)
        self._initialized = True

    def call_tool(self, name: str, arguments: dict) -> tuple[dict, dict]:
        if name not in MCP_READ_ONLY_TOOLS:
            raise PermissionError(f"MCP tool {name!r} is not on the read-only allowlist (never order/quote/notify)")
        if "email" in arguments:
            raise PermissionError("never send an email address to the MCP server")
        self._ensure_initialized()
        msg = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return _mcp_payload(msg, self.config.source_key, self.endpoint, name), msg

    def fetch_target(self, t: AggTarget) -> AggPage:
        key = self.config.source_key
        if isinstance(t, CoinGateBrand):
            args = {"brand": t.brand, "country": t.country.upper()}
            sc, msg = self.call_tool("get_gift_card", args)
            leads, notes = parse_coingate_gift_card(key, t, self.endpoint, sc), []
            tool = "get_gift_card"
        elif isinstance(t, CoinGateSearch):
            args = {"category": t.category, "country": t.country.upper(), "per_page": t.per_page, "page": 1}
            sc, msg = self.call_tool("search_gift_cards", args)
            leads, notes = parse_coingate_search(key, t, self.endpoint, sc)
            tool = "search_gift_cards"
        else:  # pragma: no cover
            raise ParserBroken(key, f"unknown target type {type(t).__name__}")
        blob = json.dumps(sc, sort_keys=True, separators=(",", ":")).encode()
        url = f"{self.endpoint}#{tool}?" + "&".join(f"{k}={v}" for k, v in args.items())
        return AggPage(target_id=t.id, url=url, http_status=msg["_status"], leads=leads,
                       body_sha256=msg["_body_sha256"], body_bytes=msg["_body_bytes"], data_sha256=_sha(blob),
                       notes=notes)


# ============================================================================== BuySellVouchers (RSC list)
_RSC_PUSH = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)
_BSV_ANCHOR = '"initialProductsList":'


class BsvPage(AggTarget):
    path: str  # /en/products/list/<category>/ - no query strings (robots: Disallow /*?)

    @field_validator("path")
    @classmethod
    def _safe_path(cls, v: str) -> str:
        if "?" in v or not v.startswith("/en/products/list/"):
            raise ValueError("BSV pages must be /en/products/list/<category>/ without query (robots.txt)")
        return v


class BsvListConfig(AggregatorConfigBase):
    host: str = "www.buysellvouchers.com"
    pages: list[BsvPage] = Field(default_factory=list)


def rsc_flight_text(html: str) -> str:
    out = []
    for chunk in _RSC_PUSH.findall(html):
        try:
            out.append(json.loads(f'"{chunk}"'))
        except json.JSONDecodeError:
            continue
    return "".join(out)


def bsv_products(key: str, url: str, html: str) -> tuple[list[dict], dict]:
    flight = rsc_flight_text(html)
    i = flight.find(_BSV_ANCHOR)
    if i < 0:
        raise ParserBroken(key, f"no initialProductsList in RSC payload of {url} (layout change?)", url=url)
    dec = json.JSONDecoder()
    try:
        arr, end = dec.raw_decode(flight, i + len(_BSV_ANCHOR))
    except json.JSONDecodeError as exc:
        raise ParserBroken(key, f"initialProductsList not decodable on {url}: {exc}", url=url) from None
    if not isinstance(arr, list):
        raise ParserBroken(key, f"initialProductsList is not a list on {url}", url=url)
    pag: dict = {}
    j = flight.find('"initialPagination":', end)
    if j >= 0:
        try:
            pag = dec.raw_decode(flight, j + len('"initialPagination":'))[0]
        except json.JSONDecodeError:
            pag = {}
    return arr, pag if isinstance(pag, dict) else {}


def bsv_seller(p: dict) -> str:
    u = p.get("user") if isinstance(p.get("user"), dict) else {}
    us = u.get("userSellers") if isinstance(u.get("userSellers"), dict) else {}
    store = str(us.get("store_name") or "").strip()
    if store:
        return store
    return pseudonym("bsv-seller", str(p.get("user_id") or u.get("username") or "unknown"))


def bsv_region(p: dict) -> str:
    regs = [r.get("geoRegion", {}).get("keyword") for r in p.get("productActivationRegions") or []
            if isinstance(r, dict) and isinstance(r.get("geoRegion"), dict)]
    ctry = []
    for c in p.get("productActivationCountries") or []:
        cc = c.get("country") if isinstance(c, dict) and isinstance(c.get("country"), dict) else c
        ctry.append(str(cc.get("code_short") or cc.get("name") or "") if isinstance(cc, dict) else str(cc))
    vals = list(dict.fromkeys(x for x in regs + ctry if x))
    return ",".join(vals) if vals else "unknown"


def parse_bsv_list(key: str, t: BsvPage, url: str, http_status: int, body: bytes) -> AggPage:
    html = body.decode("utf-8", errors="replace")
    arr, pag = bsv_products(key, url, html)
    notes = [f"pagination={ {k: pag.get(k) for k in ('total', 'pageSize', 'pageCount')} }"] if pag else []
    if not arr:
        if t.empty_ok and str(pag.get("total", "")) == "0":
            notes.append("Kategorie meldet explizit 0 Produkte")
        else:
            raise UnexpectedEmpty(key, f"initialProductsList empty on {url}", url=url, http_status=http_status)
    leads = []
    for p in arr:
        if not isinstance(p, dict) or not p.get("id") or p.get("price") is None or not p.get("currency"):
            raise ParserBroken(key, f"BSV product without id/price/currency on {url}", url=url, http_status=http_status)
        name = str(p.get("name") or "")
        face, fcur = face_from_title(name)
        qty = int(p["quantity"]) if str(p.get("quantity", "")).isdigit() else "unknown"
        active = str(p.get("is_active", "yes")).lower() == "yes"
        leads.append(AggLead(
            lead_id=f"p{p['id']}", title=name, seller=bsv_seller(p), face_value=face, face_currency=fcur,
            price=str(p["price"]), currency=str(p["currency"]).upper(),
            discount_percent=str(p.get("discount_percent_pub")) if p.get("discount_percent_pub") is not None else None,
            quantity=qty, availability="InStock" if active and qty != 0 else "OutOfStock", region=bsv_region(p),
            seller_link=url,
            raw={"id": p.get("id"), "name": name, "price": p.get("price"), "currency": p.get("currency"),
                 "quantity": p.get("quantity"), "sold": p.get("sold"), "discount_percent_pub": p.get("discount_percent_pub"),
                 "nominal_sum_pub": p.get("nominal_sum_pub"), "auction": p.get("auction"),
                 "is_api_product": p.get("is_api_product"), "seller": bsv_seller(p), "region": bsv_region(p)}))
    data = json.dumps([x.raw for x in leads], sort_keys=True, separators=(",", ":")).encode()
    return AggPage(target_id=t.id, url=url, http_status=http_status, leads=leads, body_sha256=_sha(body),
                   body_bytes=len(body), data_sha256=_sha(data), notes=notes)


class BsvListConnector(AggregatorConnector):
    PARSER_NAME = "bsv-rsc-list"
    PARSER_VERSION = "bsv-rsc-list/1.0.0"
    config: BsvListConfig

    def describe(self) -> str:
        return ("Kategorie-Listen /en/products/list/<kat>/ (RSC initialProductsList im HTML, kein Login); "
                "Verkaeufer = Store-Name, Einzelverkaeufer pseudonymisiert; Buyer-API braucht Konto+Freigabe (nicht genutzt)")

    def targets(self) -> list[AggTarget]:
        return [p.model_copy(update={"id": p.id or slugify(p.path.rstrip('/').rsplit('/', 1)[-1])})
                for p in self.config.pages]

    def fetch_target(self, t: AggTarget) -> AggPage:
        assert isinstance(t, BsvPage)
        res = self._html_get(urljoin(f"https://{self.config.host}/", t.path))
        return parse_bsv_list(self.config.source_key, t, res.url, res.status, res.body)


# ============================================================================== CardBear (brand table)
_CB_TABLE = re.compile(r'<div\s+role="table"', re.I)
_CB_ROW_SPLIT = re.compile(r'<div\s+role="row"', re.I)
_CB_ALT = re.compile(r'<img[^>]*\salt="([^"]+)"', re.I)
_CB_DISC = re.compile(r'>\s*([\d]+(?:\.\d+)?)\s*<span>%</span>', re.I)
_CB_LINK = re.compile(r'href="(https://www\.cardbear\.com/r\.php\?[^"]+)"', re.I)
_CB_STORE = re.compile(r'giftstore=([A-Za-z0-9_-]+)')
_TAGS = re.compile(r"<[^>]+>")


class CardBearPage(AggTarget):
    path: str  # /gift-card-discount/<id>/<slug>

    @field_validator("path")
    @classmethod
    def _safe_path(cls, v: str) -> str:
        if "?" in v or not re.fullmatch(r"/gift-card-discount/\d+/[a-z0-9-]+", v):
            raise ValueError("CardBear pages must be /gift-card-discount/<id>/<slug>")
        return v


class CardBearConfig(AggregatorConfigBase):
    host: str = "www.cardbear.com"
    market_currency: str = "USD"
    pages: list[CardBearPage] = Field(default_factory=list)


def _txt(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(_TAGS.sub(" ", fragment))).strip()


def parse_cardbear(key: str, t: CardBearPage, url: str, http_status: int, body: bytes,
                   market_currency: str = "USD") -> AggPage:
    html = body.decode("utf-8", errors="replace")
    m = _CB_TABLE.search(html)
    if not m:
        raise ParserBroken(key, f"no comparison table (role=table) on {url} (layout change?)", url=url,
                           http_status=http_status)
    table = html[m.start():]
    h2 = table.find("<h2")
    table = table[:h2] if h2 > 0 else table  # the table ends before the next section heading
    end = table.find('role="columnheader"')
    rows = _CB_ROW_SPLIT.split(table)[1:]
    rows = [r for r in rows if 'role="columnheader"' not in r[:3000]]
    if not rows or end < 0:
        raise UnexpectedEmpty(key, f"comparison table on {url} has no data rows", url=url, http_status=http_status)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    brand = _txt(title_m.group(1)).split(" Gift Card")[0] if title_m else t.id
    leads, oos = [], []
    for r in rows:
        r = r[:8000]
        alt = _CB_ALT.search(r)
        if not alt:
            break  # past the table
        seller = htmllib.unescape(alt.group(1)).strip()
        d = _CB_DISC.search(r)
        if not d:  # out-of-stock rows show a dash instead of a discount
            oos.append(seller)
            continue
        link = _CB_LINK.search(r)
        store = _CB_STORE.search(link.group(1)).group(1) if link and _CB_STORE.search(link.group(1)) else slugify(seller)
        leads.append(AggLead(
            lead_id=f"{slugify(store)}", title=f"{brand} gift card @ {seller}", seller=seller,
            currency=market_currency, discount_percent=d.group(1), availability="InStock", region="US",
            seller_link=htmllib.unescape(link.group(1)) if link else None,
            raw={"brand": brand, "marketplace": seller, "discount_percent": d.group(1),
                 "outbound_link_not_followed": htmllib.unescape(link.group(1)) if link else None}))
    if not leads and not oos:
        raise ParserBroken(key, f"comparison rows on {url} could not be parsed", url=url, http_status=http_status)
    notes = [f"Out of Stock laut CardBear: {', '.join(oos) or '-'}", "US-Markt, nur Rabatt-% (kein Preis, kein Nennwert)"]
    data = json.dumps([x.raw for x in leads] + [{"oos": oos}], sort_keys=True).encode()
    return AggPage(target_id=t.id, url=url, http_status=http_status, leads=leads, body_sha256=_sha(body),
                   body_bytes=len(body), data_sha256=_sha(data), notes=notes)


class CardBearConnector(AggregatorConnector):
    PARSER_NAME = "cardbear-html"
    PARSER_VERSION = "cardbear-html/1.0.0"
    config: CardBearConfig

    def describe(self) -> str:
        return "Marken-Vergleichsseiten (serverseitige Tabelle: Marktplatz + Rabatt-%), US-Markt/USD, keine Preise"

    def targets(self) -> list[AggTarget]:
        return [p.model_copy(update={"id": p.id or slugify(p.path.rsplit('/', 1)[-1])}) for p in self.config.pages]

    def fetch_target(self, t: AggTarget) -> AggPage:
        assert isinstance(t, CardBearPage)
        res = self._html_get(urljoin(f"https://{self.config.host}/", t.path))
        return parse_cardbear(self.config.source_key, t, res.url, res.status, res.body, self.config.market_currency)


# ============================================================================== GiftCardWiki (hot deals)
_GCW_ANCHOR = re.compile(r"Filter by Brand", re.I)
_GCW_ROW = re.compile(
    r'<a class="brandFilter"[^>]*>(?P<brand>[^<]+)</a>.*?<span class="text-danger">\s*(?P<disc>[\d.]+)% off\s*</span>'
    r'.*?\|\s*(?P<cards>\d+) cards\s*\|\s*<a href="(?P<href>[^"]+)"', re.S | re.I)


class GcwConfig(AggregatorConfigBase):
    host: str = "www.giftcardwiki.com"
    market_currency: str = "USD"
    pages: list[AggTarget] = Field(default_factory=lambda: [AggTarget(id="hot-deals")])
    path: str = "/hot-deals/"


def parse_gcw_hotdeals(key: str, t: AggTarget, url: str, http_status: int, body: bytes,
                       market_currency: str = "USD") -> AggPage:
    html = body.decode("utf-8", errors="replace")
    m = _GCW_ANCHOR.search(html)
    if not m:
        raise ParserBroken(key, f"no 'Filter by Brand' block on {url} (layout change?)", url=url, http_status=http_status)
    block = html[m.end():]
    block = block[: block.find("</table>")] if "</table>" in block else block
    leads = []
    for r in _GCW_ROW.finditer(block):
        brand = htmllib.unescape(r.group("brand")).strip()
        href = urljoin(url, htmllib.unescape(r.group("href")))
        leads.append(AggLead(
            lead_id=slugify(brand), title=f"{brand} (Hot Deal, {r.group('cards')} Karten)",
            seller="unknown (GiftCardWiki brand aggregate)", currency=market_currency,
            discount_percent=r.group("disc"), quantity=int(r.group("cards")), availability="InStock", region="US",
            seller_link=href, raw={"brand": brand, "discount_percent": r.group("disc"), "cards": int(r.group("cards")),
                                   "brand_page": href}))
    if not leads:
        raise UnexpectedEmpty(key, f"hot-deals brand list on {url} has 0 rows", url=url, http_status=http_status)
    markets = re.findall(r'<option[^>]*>\s*([A-Za-z][\w ]+?)\s*</option>', html)
    data = json.dumps([x.raw for x in leads], sort_keys=True).encode()
    return AggPage(target_id=t.id, url=url, http_status=http_status, leads=leads, body_sha256=_sha(body),
                   body_bytes=len(body), data_sha256=_sha(data),
                   notes=["US-Markt, Markenrabatt-% (kein Preis/Nennwert/Verkaeufer im HTML; Kartentabelle ist JS)"]
                   + ([f"Markt-Filter im HTML: {', '.join(sorted(set(markets))[:10])}"] if markets else []))


class GcwHotDealsConnector(AggregatorConnector):
    PARSER_NAME = "gcw-hotdeals"
    PARSER_VERSION = "gcw-hotdeals/1.0.0"
    config: GcwConfig

    def describe(self) -> str:
        return "Hot-Deals-Markenliste (serverseitiges HTML: Marke, Rabatt-%, Kartenanzahl), US-Markt/USD"

    def targets(self) -> list[AggTarget]:
        return list(self.config.pages)

    def fetch_target(self, t: AggTarget) -> AggPage:
        res = self._html_get(urljoin(f"https://{self.config.host}/", self.config.path))
        return parse_gcw_hotdeals(self.config.source_key, t, res.url, res.status, res.body, self.config.market_currency)


AGGREGATOR_KINDS: dict[str, tuple[type[AggregatorConfigBase], type[AggregatorConnector]]] = {
    "coingate_mcp": (CoinGateMcpConfig, CoinGateMcpConnector),
    "bsv_list": (BsvListConfig, BsvListConnector),
    "cardbear_html": (CardBearConfig, CardBearConnector),
    "gcw_hotdeals": (GcwConfig, GcwHotDealsConnector),
}


def build_aggregator(kind: str, options: dict, **kw) -> AggregatorConnector:
    cfg_cls, conn_cls = AGGREGATOR_KINDS[kind]
    return conn_cls(cfg_cls.model_validate(options), **kw)
