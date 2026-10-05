"""New-seller detection for watched marketplace/product pages.

Input: the `seller_offer` dicts the connector puts into NormalizedOffer.raw, plus the set of page URLs
that were fetched+parsed successfully in this scan. A page that failed is never used to declare offers
"gone" (that would turn a disturbance into a fake market change).

Event kinds:
- baseline         first time this page is tracked at all (initial inventory, not a "new seller")
- new_seller_offer seller offer never seen before on an already-tracked page
- returned         a previously gone offer is listed again
- price_change     listed price changed vs. last observation
- gone             offer missing on a successfully parsed page
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage.orm import SellerOfferEventRow, SellerOfferRow

log = logging.getLogger("value_rail.sellers")


def track_seller_offers(s: Session, offers: Iterable[dict[str, Any]], ok_pages: set[str], *, now: datetime,
                        scan_run_id: int | None) -> dict[str, int]:
    counts = {"baseline": 0, "new_seller_offer": 0, "returned": 0, "price_change": 0, "gone": 0}
    offers = list(offers)
    pages = {o["page_url"] for o in offers} | set(ok_pages)
    keyed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for o in offers:
        keyed[(o["source_key"], o["page_url"], o["offer_key"])] = o
    known_pages: dict[str, bool] = {}
    existing: dict[tuple[str, str, str], SellerOfferRow] = {}
    if pages:
        for row in s.scalars(select(SellerOfferRow).where(SellerOfferRow.page_url.in_(pages))).all():
            existing[(row.source_key, row.page_url, row.offer_key)] = row
            known_pages[row.page_url] = True

    def event(kind: str, o_or_row: Any, old: str = "", new: str = "") -> None:
        get = (lambda k: o_or_row[k]) if isinstance(o_or_row, dict) else (lambda k: getattr(o_or_row, k))
        s.add(SellerOfferEventRow(at=now, scan_run_id=scan_run_id, source_key=get("source_key"),
                                  page_url=get("page_url"), offer_key=get("offer_key"), seller=get("seller"),
                                  kind=kind, old_price=old, new_price=new,
                                  currency=o_or_row["currency"] if isinstance(o_or_row, dict) else o_or_row.currency))
        counts[kind] += 1
        if kind in ("new_seller_offer", "returned"):
            log.info("%s: %s on %s (%s) at %s %s", kind, get("seller"), get("page_url"), get("offer_key"), new,
                     o_or_row["currency"] if isinstance(o_or_row, dict) else o_or_row.currency)

    for k, o in keyed.items():
        price, qty = str(o.get("price", "unknown")), str(o.get("quantity", "unknown"))
        row = existing.get(k)
        if row is None:
            row = SellerOfferRow(source_key=o["source_key"], page_url=o["page_url"], offer_key=o["offer_key"],
                                 seller=o["seller"], sku=o["sku"], region=o.get("region", "unknown"),
                                 first_seen_at=now, last_seen_at=now, last_price=price, currency=o["currency"],
                                 last_quantity=qty, seen_count=1, active=True)
            s.add(row)
            event("new_seller_offer" if known_pages.get(o["page_url"]) else "baseline", o, "", price)
            continue
        if not row.active:
            event("returned", o, row.last_price, price)
        elif row.last_price != price:
            event("price_change", o, row.last_price, price)
        row.last_seen_at, row.last_price, row.currency, row.last_quantity = now, price, o["currency"], qty
        row.seen_count += 1
        row.active = True

    # gone: only on pages that were fetched and parsed successfully in this scan
    for k, row in existing.items():
        if k in keyed or not row.active or row.page_url not in ok_pages:
            continue
        row.active = False
        event("gone", row, row.last_price, "")
    s.flush()
    return counts
