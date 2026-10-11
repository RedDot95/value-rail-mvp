"""Durable public signal feed readable by a ChatGPT scheduled task.

Only public listing facts are published. No keys, account data, voucher codes,
checkout or fees. The notification policy supplies stable chained event IDs.
"""
from __future__ import annotations
from datetime import datetime

from .alerts.policy import decide
from .connectors.coingate_clearance import PAGE_URL, CoinGateClearanceConnector
from .domain.enums import RouteStatus
from .domain.timeutil import utcnow
from .settings import Settings
from .valuation.engine import evaluate_route
from .valuation.models import OfferInput, RouteInputs, RuleParams

MAX_HISTORY = 5000


def export_feed(settings: Settings, previous: dict | None = None, *, now: datetime | None = None, connector=None) -> dict:
    now = now or utcnow()
    previous = previous or {}
    connector = connector or CoinGateClearanceConnector()
    rules = RuleParams.model_validate(settings.file_config.rules.model_dump())
    if rules.evaluation_mode != 'screener':
        raise ValueError('Clearance feed requires screener mode')
    base = dict(schema_version=1, source_url=PAGE_URL, checked_at=now.isoformat(),
                rule_label=rules.label, min_discount=str(rules.price_find_min_discount))
    try:
        items = connector.discovery(now)
        if not connector.inventory_complete:
            raise ValueError('incomplete_clearance_inventory')
        old = {x['route_key']: x for x in previous.get('offers', [])}
        history = dict(previous.get('signal_history', {}))
        offers = []
        for item in items:
            normalized = connector.normalize(item, connector.offer_fetch(item, now)[0], now)
            expiry = normalized.raw.get('expires_at', 'unknown')
            inp = OfferInput(offer_ref='listing_snapshot:clearance', source_key='coingate', source_role='price_basis',
                identity=item.product, unit_price=normalized.unit_price, currency=normalized.currency,
                advertised_quantity=normalized.advertised_quantity, captured_at=now,
                listing_url=PAGE_URL, listing_title=normalized.raw['title'],
                valid_until=None if expiry == 'unknown' else expiry,
                evidence_refs=['listing_snapshot:clearance'])
            result = evaluate_route(RouteInputs(route_key=item.route_key, product=item.product, offers=[inp], evaluated_at=now), rules)
            if result.status != RouteStatus.PRICE_FIND:
                continue
            prior = old.get(item.route_key)
            decision = decide(result, prior.get('fingerprint') if prior else None,
                              prior.get('signal_id') if prior else history.get(item.route_key, 'first-observed:'+now.isoformat()), settings.file_config.alerts)
            offers.append(dict(route_key=item.route_key, **result.screening, discount=str(result.discount),
                quantity=result.advertised_quantity, signal_id=decision.event_id if decision.enqueue else prior['signal_id'],
                signal_at=now.isoformat() if decision.enqueue else prior['signal_at'],
                reason=decision.reason if decision.enqueue else prior['reason'],
                fingerprint=decision.fingerprint if decision.enqueue else prior['fingerprint']))
        for row in offers:
            history[row['route_key']] = row['signal_id']
        # Bound tombstones, not currently available candidates.
        history = dict(list(history.items())[-MAX_HISTORY:])
        offers.sort(key=lambda x: (-float(x['discount']), x['route_key']))
        return base | dict(status='ok', last_success_at=now.isoformat(), enumeration_complete=True,
            inventory_codes=connector.stats.get('observed_codes'), total_candidates=len(offers),
            offers=offers, signal_history=history)
    except Exception as exc:
        # Preserve last success, never publish potentially sensitive HTTP exception text.
        return base | dict(status='error', error_code=getattr(exc,'code',type(exc).__name__),
            last_success_at=previous.get('last_success_at'), enumeration_complete=False,
            inventory_codes=None, total_candidates=previous.get('total_candidates',0),
            offers=previous.get('offers',[]), signal_history=previous.get('signal_history',{}))
