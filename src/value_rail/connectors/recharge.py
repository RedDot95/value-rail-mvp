"""Recharge.com direct-seller connector (DE storefront) - schema.org JSON-LD parser.

Access basis (verified 2026-10-05, see docs/sources.md):
- https://www.recharge.com/robots.txt: `User-agent: *` disallows /checkout, /cart, /orders, /user,
  /account, /password, /api (except a few /api/client/* paths) and sets `Crawl-delay: 1`.
  Public product pages such as /en/de/bitsa and /en/de/paysafecard are NOT disallowed.
- The pages are served without login and embed a standard schema.org `ProductGroup` JSON-LD block
  with one `Product` per denomination (sku, gtin13, offers.price, priceCurrency, availability and a
  CompoundPriceSpecification with "Voucher Value" and "Service Fee (from)").
- We do NOT use the undocumented /api/client/* JSON endpoints and never touch checkout/cart/account.

Honest capability report:
- discovery/offer_fetch/normalize: yes (configured product pages only; no crawling).
- checkout_quote: NO. Recharge publishes no non-binding quote endpoint; the page only states a
  "Service Fee (from)" lower bound that depends on the payment method. The service fee is therefore
  modelled as a REQUIRED fee with amount "unknown" -> such routes are `blocked`, never a Preisfund.
- exit_quote: NO (the seller does not buy vouchers back; exits come from sourced RuleVersion exit rules).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

from ..domain.entities import QuantityObservation
from ..domain.enums import EvidenceKind, SourceKind, SourceRole
from ..domain.identity import ProductIdentity
from ..evidence import EvidenceDraft
from ..net.errors import FetchError, ParserBroken, UnexpectedEmpty, UpstreamError
from ..net.http_safe import PolitenessPolicy, SafeHttpClient
from ..valuation.models import FeeComponent
from .base import (Connector, ConnectorCapabilities, DiscoveryItem, NormalizedOffer, RawOffer, SourceSpec,
                   SourceUnavailable)

PARSER_NAME = "recharge-jsonld"
PARSER_VERSION = "recharge-jsonld/1.0.0"
BASE_URL = "https://www.recharge.com"
ALLOWED_HOSTS = {"www.recharge.com"}
SELLER = "recharge.com"

_LD_RE = re.compile(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)
_FACE_IN_NAME_RE = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*(EUR|€)\b", re.I)


class RechargeProduct(BaseModel):
    slug: str  # path segment after the storefront, e.g. "bitsa"
    family: str  # product family used in this app, e.g. "bitsa" / "paysafecard"
    redemption_program: str  # identity field, e.g. "bitsa" / "paysafecard"
    prerequisites: list[str] = []
    tier: str = "watch"  # watch (5-min watchlist) | discover (30-min sweep); selected per job via options.tiers


class RechargeConfig(BaseModel):
    storefront: str = "en/de"  # language/country path; country drives region + currency expectation
    region: str = "DE"
    expected_currency: str = "EUR"
    products: list[RechargeProduct] = [
        RechargeProduct(slug="bitsa", family="bitsa", redemption_program="bitsa",
                        prerequisites=["bitsa_account_kyc_eea"]),
        RechargeProduct(slug="paysafecard", family="paysafecard", redemption_program="paysafecard",
                        prerequisites=["paysafecard_refund_identity_verification_de_bank_account"]),
    ]
    min_interval_s: float = 5.0  # stricter than robots Crawl-delay: 1
    jitter_s: float = 2.0
    max_retries: int = 2


SOURCE = SourceSpec(key="recharge-com-de", name="Recharge.com (DE storefront, JSON-LD)",
                    kind=SourceKind.DIRECT_SELLER, role=SourceRole.PRICE_BASIS)


@dataclass
class ParsedVariant:
    name: str
    sku: str
    gtin13: str
    price: str
    currency: str
    availability: str
    url: str
    voucher_value: str | None
    service_fee_from: str | None
    raw: dict[str, Any]


@dataclass
class ParsedPage:
    url: str
    http_status: int
    product_group_name: str
    variants: list[ParsedVariant]
    jsonld_sha256: str
    body_sha256: str
    body_bytes: int


def extract_jsonld(html: str) -> list[Any]:
    out = []
    for block in _LD_RE.findall(html):
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError:
            continue
    return out


def _product_groups(blocks: list[Any]) -> list[dict[str, Any]]:
    flat: list[Any] = []
    for b in blocks:
        if isinstance(b, list):
            flat.extend(b)
        elif isinstance(b, dict) and isinstance(b.get("@graph"), list):
            flat.extend(b["@graph"])
        else:
            flat.append(b)
    return [x for x in flat if isinstance(x, dict) and x.get("@type") == "ProductGroup"]


def parse_page(source_key: str, url: str, http_status: int, body: bytes) -> ParsedPage:
    html = body.decode("utf-8", errors="replace")
    groups = _product_groups(extract_jsonld(html))
    if not groups:
        raise ParserBroken(source_key, f"no schema.org ProductGroup JSON-LD on {url} (layout change?)", url=url,
                           http_status=http_status)
    if len(groups) > 1:
        raise ParserBroken(source_key, f"{len(groups)} ProductGroup blocks on {url}; ambiguous", url=url,
                           http_status=http_status)
    g = groups[0]
    variants_raw = g.get("hasVariant")
    if variants_raw is None:
        raise ParserBroken(source_key, f"ProductGroup without hasVariant on {url}", url=url, http_status=http_status)
    if not isinstance(variants_raw, list) or not variants_raw:
        raise UnexpectedEmpty(source_key, f"ProductGroup on {url} lists 0 variants", url=url, http_status=http_status)
    variants: list[ParsedVariant] = []
    for v in variants_raw:
        if not isinstance(v, dict) or not isinstance(v.get("offers"), dict):
            raise ParserBroken(source_key, f"variant without offers object on {url}", url=url,
                               http_status=http_status)
        off = v["offers"]
        if "price" not in off or "priceCurrency" not in off:
            raise ParserBroken(source_key, f"variant offer without price/priceCurrency on {url}", url=url,
                               http_status=http_status)
        vv = sf = None
        spec = off.get("priceSpecification") or {}
        for comp in spec.get("priceComponent") or []:
            if not isinstance(comp, dict):
                continue
            nm = str(comp.get("name", "")).strip().lower()
            ptype = str(comp.get("priceType", ""))
            if nm == "voucher value" or ptype.endswith("/BaseService"):
                vv = str(comp.get("price"))
            elif nm.startswith("service fee") or ptype.endswith("/ServiceFee"):
                sf = str(comp.get("price"))
        variants.append(ParsedVariant(
            name=str(v.get("name", "")), sku=str(v.get("sku", "")) or "unknown", gtin13=str(v.get("gtin13", "")) or "unknown",
            price=str(off["price"]), currency=str(off["priceCurrency"]).upper(),
            availability=str(off.get("availability", "unknown")), url=str(off.get("url", "")),
            voucher_value=vv, service_fee_from=sf, raw=v))
    ld_blob = json.dumps(g, sort_keys=True, separators=(",", ":")).encode()
    return ParsedPage(url=url, http_status=http_status, product_group_name=str(g.get("name", "")), variants=variants,
                      jsonld_sha256=hashlib.sha256(ld_blob).hexdigest(), body_sha256=hashlib.sha256(body).hexdigest(),
                      body_bytes=len(body))


def _dec(s: str | None) -> Decimal | None:
    if s is None:
        return None
    try:
        d = Decimal(str(s).strip().replace(",", "."))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def face_value_of(v: ParsedVariant) -> tuple[Decimal | str, str]:
    """Face value: the 'Voucher Value' price component, else '<n> EUR' in the variant name, else unknown."""
    d = _dec(v.voucher_value)
    if d is not None and d > 0:
        return d, "jsonld:priceComponent[Voucher Value]"
    m = _FACE_IN_NAME_RE.search(v.name)
    if m:
        d = _dec(m.group(1))
        if d is not None and d > 0:
            return d, "jsonld:name"
    return "unknown", "unknown"


class RechargeConnector(Connector):
    key = "recharge"

    def __init__(self, config: RechargeConfig | None = None, *, client: SafeHttpClient | None = None) -> None:
        self.config = config or RechargeConfig()
        self.client = client or SafeHttpClient(
            source_key=SOURCE.key, allowed_hosts=ALLOWED_HOSTS,
            policy=PolitenessPolicy(min_interval_s=self.config.min_interval_s, jitter_s=self.config.jitter_s,
                                    max_retries=self.config.max_retries))
        self._pages: dict[str, tuple[ParsedPage, datetime]] = {}
        self._errors: dict[str, FetchError | SourceUnavailable] = {}
        self.active_tiers: set[str] | None = None
        self.ok_pages: set[str] = set()

    def configure_for_job(self, options: dict[str, Any]) -> None:
        tiers = options.get("tiers")
        self.active_tiers = set(tiers) if tiers else None

    def selected_products(self) -> list[RechargeProduct]:
        return [p for p in self.config.products if self.active_tiers is None or p.tier in self.active_tiers]

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            discovery=True, offer_fetch=True, normalize=True, checkout_quote=False, exit_quote=False,
            live_network=True, synthetic=False,
            notes=("Recharge.com DE product pages, schema.org JSON-LD (robots.txt permits; Crawl-delay honoured). "
                   "No checkout quote: service fee only 'from 0', payment-method dependent -> unknown/required. "
                   f"parser {PARSER_VERSION}"))

    def page_url(self, p: RechargeProduct) -> str:
        return f"{BASE_URL}/{self.config.storefront.strip('/')}/{p.slug}"

    def _fetch_page(self, p: RechargeProduct, now: datetime) -> ParsedPage:
        url = self.page_url(p)
        res = self.client.get(url)
        if res.status == 404:
            raise UpstreamError(SOURCE.key, f"product page {url} returned 404 (removed/renamed?)", url=url,
                                http_status=404)
        if not 200 <= res.status < 300:
            raise UpstreamError(SOURCE.key, f"unexpected HTTP {res.status} for {url}", url=url,
                                http_status=res.status)
        if "html" not in res.content_type.lower():
            raise ParserBroken(SOURCE.key, f"unexpected content-type {res.content_type!r} for {url}", url=url,
                               http_status=res.status)
        return parse_page(SOURCE.key, res.url, res.status, res.body)

    # ---- interface ----
    def discovery(self, now: datetime) -> list[DiscoveryItem]:
        """Fetch each configured product page once and emit one route candidate per denomination.

        A page that fails yields a single error item; offer_fetch re-raises the specific error so the
        scan marks the source as disturbed for that page instead of reporting 'no offers'.
        """
        items: list[DiscoveryItem] = []
        self._pages.clear()
        self._errors.clear()
        self.ok_pages = set()
        for p in self.selected_products():
            try:
                page = self._fetch_page(p, now)
            except SourceUnavailable as exc:
                self._errors[p.slug] = exc
                items.append(DiscoveryItem(
                    route_key=f"recharge-{self.config.region.lower()}:{p.slug}:page",
                    product=ProductIdentity(face_value="unknown", face_currency="unknown", region=self.config.region,
                                            variant="unknown", seller=SELLER, redemption_program=p.redemption_program),
                    product_family=p.family, sources=[SOURCE], prerequisites=list(p.prerequisites),
                    meta={"slug": p.slug, "page_error": True}))
                continue
            self._pages[p.slug] = (page, now)
            self.ok_pages.add(page.url)
            for v in page.variants:
                face, _src = face_value_of(v)
                ident = ProductIdentity(face_value=face, face_currency=v.currency if face != "unknown" else "unknown",
                                        region=self.config.region, variant=f"digital-code:{v.sku}", seller=SELLER,
                                        redemption_program=p.redemption_program)
                items.append(DiscoveryItem(
                    route_key=f"recharge-{self.config.region.lower()}:{p.slug}:{v.sku}", product=ident,
                    product_family=p.family, sources=[SOURCE], prerequisites=list(p.prerequisites),
                    meta={"slug": p.slug, "sku": v.sku}))
        return items

    def offer_fetch(self, item: DiscoveryItem, now: datetime) -> list[RawOffer]:
        slug = item.meta.get("slug")
        if item.meta.get("page_error"):
            raise self._errors[slug]
        if slug not in self._pages:  # called without discovery in this scan -> fetch now
            p = next(x for x in self.config.products if x.slug == slug)
            self._pages[slug] = (self._fetch_page(p, now), now)
        page, fetched_at = self._pages[slug]
        v = next((x for x in page.variants if x.sku == item.meta.get("sku")), None)
        if v is None:
            raise UnexpectedEmpty(SOURCE.key, f"variant {item.meta.get('sku')} vanished from {page.url}", url=page.url)
        return [RawOffer(source_key=SOURCE.key, fetched_at=fetched_at, payload={
            "page_url": page.url, "http_status": page.http_status, "product_group": page.product_group_name,
            "jsonld_sha256": page.jsonld_sha256, "body_sha256": page.body_sha256, "body_bytes": page.body_bytes,
            "variant": v.raw, "voucher_value": v.voucher_value, "service_fee_from": v.service_fee_from,
            "price": v.price, "currency": v.currency, "availability": v.availability, "sku": v.sku,
            "gtin13": v.gtin13, "name": v.name})]

    def normalize(self, item: DiscoveryItem, raw: RawOffer, now: datetime) -> NormalizedOffer:
        pl = raw.payload
        price = _dec(pl["price"])
        currency = pl["currency"] if pl["currency"] else "unknown"
        avail = str(pl.get("availability", "unknown"))
        if avail.endswith("/OutOfStock") or avail.endswith("/SoldOut"):
            adv = QuantityObservation(value=0, observed_at=raw.fetched_at, scope="listing:schema.org availability")
        else:  # InStock says nothing about how many units -> unknown
            adv = QuantityObservation(value="unknown", observed_at=raw.fetched_at,
                                      scope=f"listing:{avail.rsplit('/', 1)[-1]} (no unit count published)")
        sf = pl.get("service_fee_from")
        fee = FeeComponent(
            name="recharge_service_fee", kind="fixed_per_order", amount="unknown", required=True,
            evidence_ref="unknown")
        evidence = [EvidenceDraft(
            kind=EvidenceKind.LISTING_SNAPSHOT, source_key=SOURCE.key, captured_at=raw.fetched_at,
            scope="listing:product_page_jsonld",
            summary=(f"{pl['name']}: {pl['price']} {currency} ({avail.rsplit('/', 1)[-1]}); "
                     f"Service Fee (from) {sf if sf is not None else 'n/a'} - payment-method dependent, treated unknown"),
            payload={"url": pl["page_url"], "http_status": pl["http_status"], "parser": PARSER_NAME,
                     "parser_version": PARSER_VERSION, "jsonld_sha256": pl["jsonld_sha256"],
                     "body_sha256": pl["body_sha256"], "body_bytes": pl["body_bytes"], "variant_jsonld": pl["variant"],
                     "robots_txt_checked": self.client.respect_robots,
                     "fetched_at_utc": raw.fetched_at.isoformat()})]
        if price is not None and pl.get("voucher_value") is not None and _dec(pl["voucher_value"]) != price:
            note = "price differs from Voucher Value component"
        else:
            note = ""
        return NormalizedOffer(
            source=SOURCE, identity=item.product, unit_price=price if price is not None else "unknown",
            currency=currency, price_text_raw=f"{pl['price']} {pl['currency']}", price_includes_fees=False,
            fees=[fee], advertised_quantity=adv, checkout_confirmed_quantity=QuantityObservation(),
            purchased_quantity=QuantityObservation(), captured_at=raw.fetched_at, evidence=evidence,
            raw={"sku": pl["sku"], "gtin13": pl["gtin13"], "availability": avail, "service_fee_from": sf,
                 "voucher_value": pl.get("voucher_value"), "parser_version": PARSER_VERSION, "page_url": pl["page_url"],
                 "note": note,
                 "seller_offer": {"source_key": SOURCE.key, "page_url": pl["page_url"], "seller": SELLER,
                                  "sku": pl["sku"], "offer_key": f"recharge-com|{pl['sku']}", "price": pl["price"],
                                  "currency": currency, "quantity": "unknown", "region": item.product.region,
                                  "availability": avail.rsplit("/", 1)[-1]}},
            is_synthetic=False)
