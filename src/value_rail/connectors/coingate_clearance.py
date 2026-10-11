"""Only the public inventory backing https://coingate.com/gift-cards/clearance.

The page uses an Algolia search-only client and provider:resale filter. Read its public
bootstrap settings, then run the same read-only search. Never fetch normal brand stock,
follow purchase links or execute scripts. Identical denominations/regions are grouped;
the cheapest available price and the number of codes at that price are advertised.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from ..catalog import resolve_instrument
from ..domain.entities import QuantityObservation
from ..domain.identity import ProductIdentity
from ..evidence import EvidenceDraft
from ..net.errors import AccessDenied, AuthLost, ParserBroken
from ..net.http_safe import PolitenessPolicy, SafeHttpClient
from .base import Connector, ConnectorCapabilities, DiscoveryItem, NormalizedOffer, RawOffer, SourceSpec

PAGE_URL = "https://coingate.com/gift-cards/clearance"
FILTERS = "provider:resale AND resale_listable:true"
SOURCE = SourceSpec(key="coingate", name="CoinGate Clearance", kind="direct_seller", role="price_basis")
SELLER = "CoinGate Gift Cards (UAB Rewards Distributed)"
ENV_KEYS = ("NEXT_PUBLIC_ALGOLIA_APP_ID", "NEXT_PUBLIC_ALGOLIA_SEARCH_API_KEY", "NEXT_PUBLIC_ALGOLIA_GIFT_CARDS_INDEX_NAME")


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        url = dict(attrs).get("src", "")
        if tag == "script" and re.fullmatch(r"https://rewards\.coingate\.com/_next/static/immutable/chunks/[A-Za-z0-9_-]+\.js", url):
            if "turbopack-" not in url and url not in self.urls:
                self.urls.append(url)


def public_search_settings(script: str) -> dict | None:
    fields = dict(re.findall(r'(NEXT_PUBLIC_ALGOLIA_[A-Z_]+):"([^"\\]+)"', script))
    if not all(k in fields for k in ENV_KEYS):
        return None
    app, key, index = (fields[k] for k in ENV_KEYS)
    if not re.fullmatch(r"[A-Z0-9]{6,20}", app) or not re.fullmatch(r"[A-Za-z0-9+/=]{16,512}", key) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", index):
        raise ParserBroken("coingate", "invalid public Clearance search configuration")
    return dict(app_id=app, search_key=key, index=index, script_sha256=hashlib.sha256(script.encode()).hexdigest())


def _amount(value, field):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ParserBroken("coingate", f"invalid Clearance {field}") from None
    if not result.is_finite() or result <= 0:
        raise ParserBroken("coingate", f"nonpositive Clearance {field}")
    return result


def group_clearance(hits: list[dict], now: datetime) -> list[dict]:
    groups = {}
    for hit in hits:
        if hit.get("provider") != "resale" or hit.get("resale_listable") is not True:
            raise ParserBroken("coingate", "Clearance query returned a non-Clearance product")
        if hit.get("out_of_stock") is True or hit.get("status") != "available" or hit.get("locked_at") not in (None, {}):
            continue
        brand, slug = hit.get("gift_card_brand_title"), hit.get("gift_card_brand_slug")
        if not isinstance(brand, str) or not isinstance(slug, str):
            raise ParserBroken("coingate", "Clearance product has no brand identity")
        instrument = resolve_instrument(brand, slug)
        if instrument is None:
            continue
        face, price = _amount(hit.get("denomination_value"), "denomination"), _amount(hit.get("price"), "price")
        currency = hit.get("currency_iso_symbol")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ParserBroken("coingate", "Clearance currency missing or invalid")
        countries = hit.get("countries")
        if not isinstance(countries, list) or not all(isinstance(c, str) and re.fullmatch(r"[A-Z]{2}", c) for c in countries):
            raise ParserBroken("coingate", "Clearance country restrictions invalid")
        region = ",".join(sorted(set(countries))) or "unknown"
        # Algolia serializes absent nullable date fields as an empty object.
        expiry = None if hit.get("expires_at") == {} else hit.get("expires_at")
        if expiry is not None:
            if type(expiry) not in (int, float, Decimal) or expiry <= 0:
                raise ParserBroken("coingate", "Clearance expiry invalid")
            try:
                expiry = datetime.fromtimestamp(float(expiry), UTC)
            except (ValueError, OverflowError, OSError):
                raise ParserBroken("coingate", "Clearance expiry out of range") from None
            if expiry <= now:
                continue
        # The identity is stable as inventory/prices change; expiry day distinguishes short-lived stock.
        key = (slug, str(face.normalize()), currency, region, expiry.date().isoformat() if expiry else "unknown")
        if key not in groups or price < groups[key]["price"]:
            groups[key] = dict(key=key, family=instrument["key"], brand=brand, slug=slug, face=face,
                               currency=currency, region=region, price=price, expiry=expiry, ids=[str(hit["objectID"])])
        elif price == groups[key]["price"]:
            group = groups[key]
            group["ids"].append(str(hit["objectID"]))
            if expiry is not None and (group["expiry"] is None or expiry < group["expiry"]):
                group["expiry"] = expiry
    return [groups[k] for k in sorted(groups)]


class CoinGateClearanceConnector(Connector):
    key = "coingate"
    source = SOURCE

    def __init__(self, *, page_client=None, asset_client=None, search_client=None, hits_per_page=1000, max_pages=10):
        if not 1 <= hits_per_page <= 1000 or not 1 <= max_pages <= 100:
            raise ValueError("Clearance pagination must be bounded (1..1000 hits, 1..100 pages)")
        self.page_client = page_client or SafeHttpClient(source_key=self.key, allowed_hosts={"coingate.com"},
            policy=PolitenessPolicy(min_interval_s=5, jitter_s=1, max_retries=1))
        # Public browser assets/search are explicitly referenced by the permitted page. These
        # clients are limited to static scripts and the search-only query endpoint, not crawling.
        self.asset_client = asset_client or SafeHttpClient(source_key=self.key, allowed_hosts={"rewards.coingate.com"},
            respect_robots=False, policy=PolitenessPolicy(min_interval_s=5, jitter_s=1, max_retries=1))
        self.search_client = search_client
        self.client = self.page_client
        self.hits_per_page, self.max_pages = hits_per_page, max_pages
        self._settings, self._settings_at = None, None
        self._groups = {}
        self.inventory_complete = False
        self.ok_pages, self.observed_pages, self.incomplete_pages = set(), set(), set()
        self.stats = {}

    def capabilities(self):
        return ConnectorCapabilities(discovery=True, offer_fetch=True, normalize=True, live_network=True,
                                     notes="Only CoinGate Clearance; search-only public inventory, no purchase/checkout")

    def configure_for_job(self, options):
        pass

    def describe(self):
        return PAGE_URL

    def _bootstrap(self, html, now):
        if self._settings is not None and 0 <= (now-self._settings_at).total_seconds() < 3600:
            return self._settings
        scripts = _Scripts()
        scripts.feed(html)
        # The bootstrap modules are the first scripts, before page-specific/UI components.
        for url in reversed(scripts.urls[:8]):
            response = self.asset_client.get(url, accept="application/javascript")
            settings = public_search_settings(response.text())
            if settings:
                if self._settings and self._settings["app_id"] != settings["app_id"]:
                    self.search_client = None
                self._settings, self._settings_at = settings, now
                return settings
        raise ParserBroken(self.key, "Clearance public search configuration missing (page changed)")

    def discovery(self, now):
        self.inventory_complete = False
        self.ok_pages, self.observed_pages, self.incomplete_pages = set(), set(), set()
        response = self.page_client.get(PAGE_URL)
        if response.url != PAGE_URL or "clearance" not in response.text().lower():
            raise ParserBroken(self.key, "Clearance page missing or redirected", url=PAGE_URL)
        settings = self._bootstrap(response.text(), now)
        host = settings["app_id"].lower()+"-dsn.algolia.net"
        search = self.search_client or SafeHttpClient(source_key=self.key, allowed_hosts={host}, respect_robots=False,
            policy=PolitenessPolicy(min_interval_s=5, jitter_s=1, max_retries=1))
        self.search_client = search
        endpoint = "https://"+host+"/1/indexes/*/queries"
        hits, ids, proofs = [], set(), []
        total = pages = None
        exhaustive = True
        for number in range(self.max_pages):
            body = {"requests":[dict(indexName=settings["index"],query="",filters=FILTERS,page=number,
                hitsPerPage=self.hits_per_page,analytics=False,attributesToHighlight=[])]}
            try:
                result = search.post_json(endpoint,json.dumps(body).encode(),extra_headers={
                    "x-algolia-application-id":settings["app_id"],"x-algolia-api-key":settings["search_key"]})
            except (AccessDenied, AuthLost):
                self._settings = None
                self.search_client = None
                raise
            try:
                data = json.loads(result.body, parse_float=Decimal)
                page = data["results"][0]
                rows = page["hits"]
            except (ValueError, KeyError, IndexError, TypeError):
                raise ParserBroken(self.key, "invalid Clearance search response") from None
            count, page_count = page.get("nbHits"), page.get("nbPages")
            if (type(count) is not int or count < 0 or type(page_count) is not int or page_count < 0
                    or type(page.get("page")) is not int or page["page"] != number
                    or page.get("hitsPerPage") != self.hits_per_page or not isinstance(rows,list)
                    or (count > 0 and page_count < 1)):
                raise ParserBroken(self.key, "invalid Clearance pagination")
            if total is None:
                total, pages = count, page_count
            elif count != total or page_count != pages:
                raise ParserBroken(self.key, "Clearance inventory changed during pagination; retry next scan")
            if len(rows) != min(self.hits_per_page,max(0,total-number*self.hits_per_page)):
                raise ParserBroken(self.key, "Clearance page length differs from declared inventory")
            for hit in rows:
                if not isinstance(hit,dict) or not str(hit.get("objectID","")).isdigit():
                    raise ParserBroken(self.key, "Clearance hit has no stable code ID")
                identity = str(hit["objectID"])
                if identity in ids:
                    raise ParserBroken(self.key, "duplicate Clearance code across pages")
                ids.add(identity)
            exhaustive = exhaustive and page.get("exhaustiveNbHits", True) is not False
            hits.extend(rows)
            proofs.append(dict(page=number,sha256=hashlib.sha256(result.body).hexdigest(),http_status=result.status))
            if number+1 >= pages:
                break
        groups = group_clearance(hits, now)
        self.inventory_complete = len(hits)==total and exhaustive
        self.observed_pages = {PAGE_URL}
        self.ok_pages = {PAGE_URL} if self.inventory_complete else set()
        self.incomplete_pages = set() if self.inventory_complete else {PAGE_URL}
        self._groups = {}
        items = []
        self._proof = dict(page_url=PAGE_URL,page_sha256=hashlib.sha256(response.body).hexdigest(),
                          pages=proofs,total_codes=total,observed_codes=len(hits),enumeration_complete=self.inventory_complete)
        for group in groups:
            identity_key = hashlib.sha256(json.dumps(group["key"]).encode()).hexdigest()[:20]
            route = "coingate:clearance:"+identity_key
            product = ProductIdentity(face_value=group["face"],face_currency=group["currency"],region=group["region"],
                variant="clearance:"+identity_key,seller=SELLER,redemption_program=group["family"])
            item = DiscoveryItem(route_key=route,product=product,product_family=group["family"],sources=[SOURCE],
                                 meta={"title":group["brand"]})
            self._groups[route] = group
            items.append(item)
        self.stats = dict(observed_codes=len(hits),groups=len(groups),enumeration_complete=self.inventory_complete)
        return items

    def offer_fetch(self, item, now):
        return [RawOffer(source_key=self.key,fetched_at=now,payload=self._groups[item.route_key])]

    def normalize(self, item, raw, now):
        group = raw.payload
        quantity = QuantityObservation(value=len(group["ids"]),observed_at=raw.fetched_at,scope="Clearance codes at observed minimum price")
        evidence = EvidenceDraft(kind="listing_snapshot",source_key=self.key,captured_at=raw.fetched_at,
            summary="CoinGate Clearance inventory; concrete denomination, price and code count",payload=self._proof | {
                "code_ids":group["ids"],"price":str(group["price"]),"face":str(group["face"]),
                "currency":group["currency"],"region":group["region"]})
        seller_offer = dict(source_key=self.key,page_url=PAGE_URL,offer_key=item.route_key,seller=SELLER,
                            sku=item.product.key_hash(),region=group["region"],price=str(group["price"]),
                            currency=group["currency"],quantity=len(group["ids"]))
        return NormalizedOffer(source=SOURCE,identity=item.product,unit_price=group["price"],currency=group["currency"],
            price_text_raw=str(group["price"]),price_includes_fees=False,fees=[],advertised_quantity=quantity,
            checkout_confirmed_quantity=QuantityObservation(),purchased_quantity=QuantityObservation(),captured_at=raw.fetched_at,
            evidence=[evidence],raw=dict(page_url=PAGE_URL,title=group["brand"]+" "+str(group["face"])+" "+group["currency"],
                expires_at=group["expiry"].isoformat() if group["expiry"] else "unknown",code_ids=group["ids"],seller_offer=seller_offer))
