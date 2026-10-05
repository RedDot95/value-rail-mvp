"""Generic schema.org JSON-LD `Product.offers[]` connector for direct sellers and marketplaces.

Used for sources whose public product pages (robots.txt-allowed, no login, plain HTTP, no JS) embed a
schema.org `Product` with an `offers` list (see docs/sources.md for the per-source access basis):

- dundle.com   (direct seller; offers[] = one Offer per denomination, price in priceSpecification)
- gamivo.com   (marketplace; offers[] = one Offer per *seller* with `seller.name`)

What it does / does not do (honest capabilities):
- discovery/offer_fetch/normalize for the configured pages only (no crawling, no search pages,
  no sitemap walking, no internal API calls, never cart/checkout/account).
- One route candidate per (page, variant/sku, seller) -> each marketplace seller offer is its own route,
  so a new seller on a watched page shows up as a new route + a `seller_offer_events` row (worker/sellers.py).
- checkout_quote: NO (fees are only shown in the cart; we never open it) -> a REQUIRED fee with amount
  "unknown" is attached, so every route is `blocked` (never a Preisfund) until a checkout quote is evidenced.
- exit_quote: NO (exits come from sourced RuleVersion exit rules).
- Aggregator sources (role discovery_only) may be configured with this parser too; their offers are
  stored as leads only and can never be a price basis (enforced by the valuation engine).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, model_validator

from ..domain.entities import QuantityObservation
from ..domain.enums import EvidenceKind, SourceKind, SourceRole
from ..domain.identity import ProductIdentity
from ..evidence import EvidenceDraft
from ..net.errors import FetchError, ParserBroken, UnexpectedEmpty, UpstreamError
from ..net.http_safe import PolitenessPolicy, SafeHttpClient
from ..valuation.models import FeeComponent
from .base import (Connector, ConnectorCapabilities, DiscoveryItem, NormalizedOffer, RawOffer, SourceSpec,
                   SourceUnavailable)

PARSER_NAME = "jsonld-offers"
PARSER_VERSION = "jsonld-offers/1.0.0"

_LD_RE = re.compile(r"<script[^>]*type=[\"']?application/ld\+json[\"']?[^>]*>(.*?)</script>", re.S | re.I)
_FACE_RES = [
    re.compile(r"(?<![\d.,])(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:EUR|€)(?![a-z])", re.I),   # "50 EUR", "50€"
    re.compile(r"(?:EUR|€)\s*(\d{1,4}(?:[.,]\d{1,2})?)(?![\d])", re.I),               # "€50", "EUR 50"
    re.compile(r"-(\d{1,4})-eur(?:-|$)", re.I),                                       # sku "paysafecard-50-eur-de"
]
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    return _SLUG_RE.sub("-", (s or "").lower()).strip("-") or "unknown"


class ShopPage(BaseModel):
    path: str  # absolute path on the configured host, e.g. "/de/paysafecard/"
    family: str  # product family in this app ("paysafecard", "bitsa", "crypto_voucher", ...)
    redemption_program: str
    region: str  # voucher region as sold on that page (e.g. "DE", "EU")
    tier: Literal["watch", "discover"] = "watch"  # watch = 5-min watchlist; discover = 30-min new-seller sweep
    prerequisites: list[str] = []
    absent_ok: bool = False  # page may legitimately list no Product (e.g. currently not sold) -> 0 offers, not an error
    note: str = ""


class JsonLdShopConfig(BaseModel):
    source_key: str
    source_name: str
    host: str
    source_kind: Literal["direct_seller", "marketplace", "aggregator"]
    fixed_seller: str | None = None  # direct sellers: the shop itself; marketplaces: None -> offer.seller.name
    expected_currency: str = "EUR"
    fee_name: str = "service_fee"
    fee_note: str = "fees only shown in cart/checkout (not opened) -> unknown"
    pages: list[ShopPage] = []
    min_interval_s: float = 5.0
    jitter_s: float = 2.0
    max_retries: int = 2

    @model_validator(mode="after")
    def _check(self) -> "JsonLdShopConfig":
        if self.min_interval_s < 5.0:
            raise ValueError("min_interval_s must be >= 5 s per host (politeness floor)")
        if self.source_kind == "direct_seller" and not self.fixed_seller:
            raise ValueError("direct_seller sources need fixed_seller")
        for p in self.pages:
            if not p.path.startswith("/"):
                raise ValueError(f"page path must be absolute: {p.path!r}")
        return self

    @property
    def role(self) -> SourceRole:
        return SourceRole.DISCOVERY_ONLY if self.source_kind == "aggregator" else SourceRole.PRICE_BASIS

    @property
    def kind(self) -> SourceKind:
        return {"direct_seller": SourceKind.DIRECT_SELLER, "marketplace": SourceKind.MARKETPLACE,
                "aggregator": SourceKind.AGGREGATOR}[self.source_kind]


@dataclass
class ParsedOffer:
    seller: str
    sku: str
    name: str
    price: str
    currency: str
    availability: str
    face_value: Decimal | str
    face_source: str
    quantity: int | str  # "unknown" unless the structured data states it
    raw: dict[str, Any]
    duplicates: int = 0  # further offers of the same seller+sku on that page (kept: cheapest)


@dataclass
class ParsedShopPage:
    url: str
    http_status: int
    product_name: str
    offers: list[ParsedOffer]
    jsonld_sha256: str
    body_sha256: str
    body_bytes: int
    absent: bool = False
    notes: list[str] = field(default_factory=list)


def extract_jsonld(html: str) -> list[Any]:
    out = []
    for block in _LD_RE.findall(html):
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError:
            continue
    return out


def _flatten(blocks: list[Any]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    stack = list(blocks)
    while stack:
        b = stack.pop(0)
        if isinstance(b, list):
            stack[0:0] = b
        elif isinstance(b, dict):
            if isinstance(b.get("@graph"), list):
                stack[0:0] = b["@graph"]
            else:
                flat.append(b)
    return flat


def _is_type(node: dict[str, Any], t: str) -> bool:
    ty = node.get("@type")
    return ty == t or (isinstance(ty, list) and t in ty)


def _dec(s: Any) -> Decimal | None:
    if s is None or isinstance(s, bool):
        return None
    try:
        d = Decimal(str(s).strip().replace(",", "."))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def face_value_from(*texts: str) -> tuple[Decimal | str, str]:
    for label, t in texts_with_labels(texts):
        for rx in _FACE_RES:
            m = rx.search(t or "")
            if m:
                d = _dec(m.group(1))
                if d is not None and d > 0:
                    return d, label
    return "unknown", "unknown"


def texts_with_labels(texts: tuple[str, ...]):
    labels = ["jsonld:offer.sku", "jsonld:offer.name", "jsonld:product.name"]
    for i, t in enumerate(texts):
        yield labels[i] if i < len(labels) else f"text{i}", t


def _offer_list(product: dict[str, Any]) -> list[dict[str, Any]]:
    offers = product.get("offers")
    if isinstance(offers, dict):
        offers = [offers]
    if not isinstance(offers, list):
        return []
    out: list[dict[str, Any]] = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        if _is_type(o, "AggregateOffer") and isinstance(o.get("offers"), list):
            out.extend(x for x in o["offers"] if isinstance(x, dict))
        elif _is_type(o, "AggregateOffer"):
            continue  # low/high range only - not an individual offer
        else:
            out.append(o)
    return out


def parse_shop_page(cfg: JsonLdShopConfig, page: ShopPage, url: str, http_status: int, body: bytes) -> ParsedShopPage:
    key = cfg.source_key
    html = body.decode("utf-8", errors="replace")
    nodes = _flatten(extract_jsonld(html))
    products = [n for n in nodes if _is_type(n, "Product") and "offers" in n]
    body_sha = hashlib.sha256(body).hexdigest()
    if not products:
        if page.absent_ok:
            return ParsedShopPage(url=url, http_status=http_status, product_name="", offers=[], jsonld_sha256="",
                                  body_sha256=body_sha, body_bytes=len(body), absent=True,
                                  notes=["no schema.org Product with offers on page (absent_ok) -> not listed now"])
        raise ParserBroken(key, f"no schema.org Product with offers JSON-LD on {url} (layout change?)", url=url,
                           http_status=http_status)
    if len(products) > 1:
        raise ParserBroken(key, f"{len(products)} Product blocks with offers on {url}; ambiguous", url=url,
                           http_status=http_status)
    prod = products[0]
    raw_offers = _offer_list(prod)
    if not raw_offers:
        raise UnexpectedEmpty(key, f"Product on {url} lists 0 individual offers", url=url, http_status=http_status)
    pname = str(prod.get("name", ""))
    by_key: dict[tuple[str, str], ParsedOffer] = {}
    for o in raw_offers:
        spec = o.get("priceSpecification") if isinstance(o.get("priceSpecification"), dict) else {}
        price = o.get("price", spec.get("price"))
        currency = o.get("priceCurrency", spec.get("priceCurrency"))
        if price is None or not currency:
            raise ParserBroken(key, f"offer without price/priceCurrency on {url}", url=url, http_status=http_status)
        if cfg.fixed_seller:
            seller = cfg.fixed_seller
        else:
            s = o.get("seller")
            seller = str(s.get("name", "")).strip() if isinstance(s, dict) else ""
            if not seller:
                raise ParserBroken(key, f"marketplace offer without seller.name on {url}", url=url,
                                   http_status=http_status)
        sku = str(o.get("sku") or prod.get("sku") or "unknown")
        oname = str(o.get("name", ""))
        face, face_src = face_value_from(str(o.get("sku", "")), oname, pname)
        qty: int | str = "unknown"
        inv = o.get("inventoryLevel")
        if isinstance(inv, dict) and _dec(inv.get("value")) is not None:
            qty = int(_dec(inv.get("value")))
        po = ParsedOffer(seller=seller, sku=sku, name=oname or pname, price=str(price), currency=str(currency).upper(),
                         availability=str(o.get("availability", "unknown")), face_value=face, face_source=face_src,
                         quantity=qty, raw=o)
        k = (slugify(seller), sku)
        prev = by_key.get(k)
        if prev is None:
            by_key[k] = po
        else:
            keep, other = (po, prev) if (_dec(po.price) or Decimal("Infinity")) < (_dec(prev.price) or Decimal("Infinity")) else (prev, po)
            keep.duplicates = prev.duplicates + 1
            by_key[k] = keep
    blob = json.dumps(prod, sort_keys=True, separators=(",", ":")).encode()
    return ParsedShopPage(url=url, http_status=http_status, product_name=pname, offers=list(by_key.values()),
                          jsonld_sha256=hashlib.sha256(blob).hexdigest(), body_sha256=body_sha, body_bytes=len(body))


class JsonLdShopConnector(Connector):
    key = "jsonld_shop"

    def __init__(self, config: JsonLdShopConfig, *, client: SafeHttpClient | None = None) -> None:
        self.config = config
        self.key = config.source_key
        self.source = SourceSpec(key=config.source_key, name=config.source_name, kind=config.kind, role=config.role)
        self.client = client or SafeHttpClient(
            source_key=config.source_key, allowed_hosts={config.host},
            policy=PolitenessPolicy(min_interval_s=config.min_interval_s, jitter_s=config.jitter_s,
                                    max_retries=config.max_retries))
        self.active_tiers: set[str] | None = None  # None = all tiers
        self._pages: dict[str, tuple[ParsedShopPage, datetime]] = {}
        self._errors: dict[str, FetchError | SourceUnavailable] = {}
        self.ok_pages: set[str] = set()

    # ---- job wiring ----
    def configure_for_job(self, options: dict[str, Any]) -> None:
        tiers = options.get("tiers")
        self.active_tiers = set(tiers) if tiers else None

    def selected_pages(self) -> list[ShopPage]:
        return [p for p in self.config.pages if self.active_tiers is None or p.tier in self.active_tiers]

    def capabilities(self) -> ConnectorCapabilities:
        c = self.config
        return ConnectorCapabilities(
            discovery=True, offer_fetch=True, normalize=True, checkout_quote=False, exit_quote=False,
            live_network=True, synthetic=False,
            notes=(f"{c.source_name}: configured public product pages, schema.org Product.offers JSON-LD "
                   f"({'seller per offer' if not c.fixed_seller else 'single seller ' + c.fixed_seller}); "
                   f"role {c.role.value}; robots.txt + >=5 s/host + jitter. No checkout quote ({c.fee_note}). "
                   f"parser {PARSER_VERSION}"))

    def page_url(self, p: ShopPage) -> str:
        return urljoin(f"https://{self.config.host}/", p.path)

    def _fetch_page(self, p: ShopPage) -> ParsedShopPage:
        url = self.page_url(p)
        res = self.client.get(url)
        key = self.config.source_key
        if res.status == 404:
            raise UpstreamError(key, f"product page {url} returned 404 (removed/renamed?)", url=url, http_status=404)
        if not 200 <= res.status < 300:
            raise UpstreamError(key, f"unexpected HTTP {res.status} for {url}", url=url, http_status=res.status)
        if "html" not in res.content_type.lower():
            raise ParserBroken(key, f"unexpected content-type {res.content_type!r} for {url}", url=url,
                               http_status=res.status)
        return parse_shop_page(self.config, p, res.url, res.status, res.body)

    def _page_id(self, p: ShopPage) -> str:
        return slugify(urlsplit(self.page_url(p)).path)

    def discovery(self, now: datetime) -> list[DiscoveryItem]:
        items: list[DiscoveryItem] = []
        self._pages.clear()
        self._errors.clear()
        self.ok_pages = set()
        c = self.config
        for p in self.selected_pages():
            pid = self._page_id(p)
            try:
                page = self._fetch_page(p)
            except SourceUnavailable as exc:
                self._errors[pid] = exc
                items.append(DiscoveryItem(
                    route_key=f"{c.source_key}:{pid}:page",
                    product=ProductIdentity(face_value="unknown", face_currency="unknown", region=p.region,
                                            variant="unknown", seller=c.fixed_seller or "unknown",
                                            redemption_program=p.redemption_program),
                    product_family=p.family, sources=[self.source], prerequisites=list(p.prerequisites),
                    meta={"page_id": pid, "page_error": True}))
                continue
            self._pages[pid] = (page, now)
            self.ok_pages.add(page.url)
            for o in page.offers:
                face = o.face_value
                ident = ProductIdentity(
                    face_value=face, face_currency=o.currency if face != "unknown" else "unknown", region=p.region,
                    variant=f"digital-code:{o.sku}", seller=o.seller, redemption_program=p.redemption_program)
                items.append(DiscoveryItem(
                    route_key=f"{c.source_key}:{pid}:{slugify(o.sku)}:{slugify(o.seller)}", product=ident,
                    product_family=p.family, sources=[self.source], prerequisites=list(p.prerequisites),
                    meta={"page_id": pid, "sku": o.sku, "seller": o.seller, "tier": p.tier}))
        return items

    def offer_fetch(self, item: DiscoveryItem, now: datetime) -> list[RawOffer]:
        pid = item.meta.get("page_id")
        if item.meta.get("page_error"):
            raise self._errors[pid]
        if pid not in self._pages:
            p = next(x for x in self.config.pages if self._page_id(x) == pid)
            self._pages[pid] = (self._fetch_page(p), now)
        page, fetched_at = self._pages[pid]
        o = next((x for x in page.offers if x.sku == item.meta.get("sku") and x.seller == item.meta.get("seller")), None)
        if o is None:
            raise UnexpectedEmpty(self.config.source_key, f"offer {item.meta.get('seller')}/{item.meta.get('sku')} "
                                  f"vanished from {page.url}", url=page.url)
        return [RawOffer(source_key=self.config.source_key, fetched_at=fetched_at, payload={
            "page_url": page.url, "http_status": page.http_status, "product_name": page.product_name,
            "jsonld_sha256": page.jsonld_sha256, "body_sha256": page.body_sha256, "body_bytes": page.body_bytes,
            "offer": o.raw, "seller": o.seller, "sku": o.sku, "name": o.name, "price": o.price, "currency": o.currency,
            "availability": o.availability, "face_source": o.face_source, "quantity": o.quantity,
            "duplicates": o.duplicates, "tier": item.meta.get("tier")})]

    def normalize(self, item: DiscoveryItem, raw: RawOffer, now: datetime) -> NormalizedOffer:
        c = self.config
        pl = raw.payload
        price = _dec(pl["price"])
        avail = str(pl.get("availability", "unknown"))
        short = avail.rsplit("/", 1)[-1]
        if short in ("OutOfStock", "SoldOut", "Discontinued"):
            adv = QuantityObservation(value=0, observed_at=raw.fetched_at, scope="listing:schema.org availability")
        elif isinstance(pl.get("quantity"), int):
            adv = QuantityObservation(value=pl["quantity"], observed_at=raw.fetched_at,
                                      scope="listing:schema.org inventoryLevel")
        else:
            adv = QuantityObservation(value="unknown", observed_at=raw.fetched_at,
                                      scope=f"listing:{short} (no unit count published)")
        fee = FeeComponent(name=f"{slugify(c.source_key)}_{c.fee_name}", kind="fixed_per_order", amount="unknown",
                           required=True, evidence_ref="unknown", note=c.fee_note)
        seller_offer = {"source_key": c.source_key, "page_url": pl["page_url"], "seller": pl["seller"],
                        "sku": pl["sku"], "offer_key": f"{slugify(pl['seller'])}|{pl['sku']}",
                        "price": pl["price"], "currency": pl["currency"], "quantity": pl.get("quantity", "unknown"),
                        "region": item.product.region, "availability": short}
        evidence = [EvidenceDraft(
            kind=EvidenceKind.LISTING_SNAPSHOT, source_key=c.source_key, captured_at=raw.fetched_at,
            scope="listing:product_page_jsonld",
            summary=(f"{pl['name']} - seller {pl['seller']}: {pl['price']} {pl['currency']} ({short}); "
                     f"{c.fee_note}"),
            payload={"url": pl["page_url"], "http_status": pl["http_status"], "parser": PARSER_NAME,
                     "parser_version": PARSER_VERSION, "jsonld_sha256": pl["jsonld_sha256"],
                     "body_sha256": pl["body_sha256"], "body_bytes": pl["body_bytes"], "offer_jsonld": pl["offer"],
                     "robots_txt_checked": self.client.respect_robots, "source_role": c.role.value,
                     "fetched_at_utc": raw.fetched_at.isoformat()})]
        return NormalizedOffer(
            source=self.source, identity=item.product, unit_price=price if price is not None else "unknown",
            currency=pl["currency"] or "unknown", price_text_raw=f"{pl['price']} {pl['currency']}",
            price_includes_fees=False, fees=[fee], advertised_quantity=adv,
            checkout_confirmed_quantity=QuantityObservation(), purchased_quantity=QuantityObservation(),
            captured_at=raw.fetched_at, evidence=evidence,
            raw={"sku": pl["sku"], "seller": pl["seller"], "availability": avail, "face_source": pl["face_source"],
                 "parser_version": PARSER_VERSION, "page_url": pl["page_url"], "duplicates": pl["duplicates"],
                 "source_role": c.role.value, "seller_offer": seller_offer},
            is_synthetic=False)
