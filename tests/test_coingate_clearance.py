"""Synthetic public-page responses: Clearance-only inventory and push lifecycle."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from value_rail.alerts.dispatcher import dispatch_pending
from value_rail.alerts.eligibility import delivery_check
from value_rail.alerts.sinks import MemorySink, TelegramAlertSink
from value_rail.connectors.coingate_clearance import CoinGateClearanceConnector, PAGE_URL, FILTERS, group_clearance, public_search_settings
from value_rail.net.errors import ParserBroken
from value_rail.storage.orm import RouteEvaluationRow, SellerOfferRow
from value_rail.valuation.replay import replay_evaluation
from value_rail.web.views import monitored_evaluations
from value_rail.worker.scan import run_scan

from .recorded import make_client
from .test_screener import configure

ASSET = 'https://rewards.coingate.com/_next/static/immutable/chunks/bootstrap.js'
API = 'https://testapp123-dsn.algolia.net/1/indexes/*/queries'
KEY = 'testpublicsearchkey123456'
SCRIPT = f'NEXT_PUBLIC_ALGOLIA_APP_ID:"TESTAPP123",NEXT_PUBLIC_ALGOLIA_SEARCH_API_KEY:"{KEY}",NEXT_PUBLIC_ALGOLIA_GIFT_CARDS_INDEX_NAME:"test_clearance"'


def code(now, id='1', **changes):
    return dict(objectID=id, provider='resale', resale_listable=True, status='available', locked_at={},
        out_of_stock=False, gift_card_brand_title='Paysafecard', gift_card_brand_slug='paysafecard',
        denomination_value=10, price=8, price_no_discount=11, discount=28, currency_iso_symbol='EUR',
        countries=['BE'], expires_at=int((now + timedelta(days=2)).timestamp())) | changes


def connector(hits, *, size=1000, max_pages=10, declared_total=None):
    state = {'hits': hits}
    page, pt, _ = make_client({
        'https://coingate.com/robots.txt': (200, {}, b'User-agent: *\nDisallow: /checkout\n'),
        PAGE_URL: (200, {}, f'<html>Clearance<script src="{ASSET}"></script></html>'.encode())}, allowed=['coingate.com'])
    assets, at, _ = make_client({ASSET:(200,{},SCRIPT.encode())},allowed=['rewards.coingate.com'],respect_robots=False)
    def response():
        body = json.loads(st.calls[-1]['body'])
        req = body['requests'][0]
        assert req['filters'] == FILTERS and req['query'] == '' and req['indexName'] == 'test_clearance'
        assert req['analytics'] is False
        n = req['page']
        count = len(state['hits']) if declared_total is None else declared_total
        result = dict(hits=state['hits'][n*size:(n+1)*size], nbHits=count, nbPages=(count+size-1)//size,
                      page=n, hitsPerPage=size)
        return (200, {}, json.dumps({'results':[result]}).encode())
    search, st, _ = make_client({API:response},allowed=['testapp123-dsn.algolia.net'],respect_robots=False)
    c = CoinGateClearanceConnector(page_client=page,asset_client=assets,search_client=search,hits_per_page=size,max_pages=max_pages)
    return c, state, (pt,at,st)


def test_read_only_bootstrap_grouping_and_nominal_discount(ctx, now):
    configure(ctx, now)
    c, state, transports = connector([code(now),code(now,'2'),code(now,'3',price=9),
        code(now,'4',gift_card_brand_title='Steam',gift_card_brand_slug='steam'),code(now,'5',locked_at=123)])
    rep = run_scan(ctx.session_factory,c,ctx.settings,now)
    assert rep.status == 'ok' and rep.items_seen == rep.offers_seen == rep.alerts_enqueued == 1
    assert c.stats == dict(observed_codes=5,groups=1,enumeration_complete=True)
    with ctx.session_factory() as s:
        ev = s.get(RouteEvaluationRow,next(iter(rep.evaluation_ids.values())))
        assert Decimal(ev.outputs['discount']) == Decimal('.2')  # not the site's 28% retail discount
        assert ev.outputs['advertised_quantity'] == 2 and ev.outputs['screening']['region'] == 'BE'
        assert replay_evaluation(s,ev.id).match
        assert KEY not in json.dumps(ev.inputs) and KEY not in json.dumps(ev.outputs)
    assert all('/gift-cards/' not in call['url'] or call['url'] == PAGE_URL for call in transports[0].calls)
    assert transports[2].calls[0]['headers']['x-algolia-api-key'] == KEY
    assert KEY not in transports[2].calls[0]['url']


def test_pagination_complete_and_partial_does_not_infer_disappearance(now):
    hits = [code(now,str(i)) for i in range(5)]
    full,_,t = connector(hits,size=2)
    assert len(full.discovery(now)) == 1 and full.inventory_complete and len(t[2].calls) == 3
    partial,_,_ = connector(hits,size=2,max_pages=1)
    assert len(partial.discovery(now)) == 1
    assert partial.incomplete_pages == {PAGE_URL} and partial.ok_pages == set()


def test_duplicate_ids_and_wrong_inventory_count_fail_closed(now):
    for hits,total in [([code(now),code(now)],None),([code(now)],2)]:
        c,_,_ = connector(hits,declared_total=total)
        with pytest.raises(ParserBroken):
            c.discovery(now)
        assert not c.inventory_complete and not c.ok_pages


@pytest.mark.parametrize('change', [dict(provider='regular'),dict(resale_listable=False),dict(price='NaN'),
    dict(price=0),dict(currency_iso_symbol=None),dict(countries=['Belgium']),dict(expires_at=-1)])
def test_invalid_search_facts_cannot_become_signals(now, change):
    with pytest.raises(ParserBroken):
        group_clearance([code(now,**change)],now)


@pytest.mark.parametrize('change', [dict(out_of_stock=True),dict(status='sold'),dict(locked_at=123),
    dict(expires_at=1),dict(gift_card_brand_title='Netflix',gift_card_brand_slug='netflix')])
def test_unavailable_expired_or_excluded_codes_are_skipped(now, change):
    assert group_clearance([code(now,**change)],now) == []


def test_public_bootstrap_rejects_untrusted_host_values():
    assert public_search_settings(SCRIPT)['app_id'] == 'TESTAPP123'
    with pytest.raises(ParserBroken):
        public_search_settings(SCRIPT.replace('TESTAPP123','evil.example/path'))
    assert public_search_settings('No search configuration here') is None


def test_clearance_push_dedup_gone_return_and_partial_inventory(ctx, now):
    configure(ctx,now)
    c,state,_ = connector([code(now)])
    sink = MemorySink()
    def scan(t):
        return run_scan(ctx.session_factory,c,ctx.settings,now+timedelta(seconds=t))
    def dispatch(t):
        return dispatch_pending(ctx.session_factory,sink,now+timedelta(seconds=t),eligibility=delivery_check(ctx.settings))
    assert scan(0).alerts_enqueued == 1 and dispatch(0).sent == 1
    assert scan(10).alerts_enqueued == 0
    state['hits'].append(code(now,'2'))
    assert scan(20).alerts_enqueued == 1 and dispatch(20).sent == 1
    state['hits'][0]['price'] = 7
    assert scan(30).alerts_enqueued == 1
    state['hits'] = []
    assert scan(40).seller_events['gone'] == 1
    assert dispatch(40).suppressed == 1
    with ctx.session_factory() as s:
        assert not s.scalar(select(SellerOfferRow)).active
        # Enable real production-only presentation/delivery policy.
        from value_rail.settings import ConnectorConfig
        ctx.settings.file_config.connectors = [ConnectorConfig(key='coingate',kind='coingate_clearance',enabled=True)]
        ctx.settings.file_config.scope.allowed_source_keys = ['coingate']
        assert monitored_evaluations(s,ctx.settings) == []
    state['hits'] = [code(now,price=7)]
    assert scan(50).alerts_enqueued == 1 and dispatch(50).sent == 1
    text = TelegramAlertSink.format_text(sink.sent[-1])
    assert PAGE_URL in text and '7 EUR' in text and 'BE' in text and 'Profit' not in text


def test_pending_expiry_is_rechecked_at_delivery(ctx, now):
    configure(ctx,now)
    c,_,_ = connector([code(now,expires_at=int((now+timedelta(seconds=5)).timestamp()))])
    run_scan(ctx.session_factory,c,ctx.settings,now)
    report = dispatch_pending(ctx.session_factory,MemorySink(),now+timedelta(seconds=6),eligibility=delivery_check(ctx.settings))
    assert report.suppressed == 1 and report.sent == 0


def test_nullable_public_date_objects_are_not_reservations_or_expiry(now):
    groups = group_clearance([code(now, locked_at={}, expires_at={})], now)
    assert len(groups) == 1 and groups[0]['expiry'] is None


def test_partial_scan_does_not_mark_unseen_groups_gone(ctx, now):
    configure(ctx,now)
    hits = [code(now,'1'),code(now,'2',denomination_value=20,price=16)]
    full,_,_ = connector(hits,size=1)
    assert run_scan(ctx.session_factory,full,ctx.settings,now).items_seen == 2
    partial,_,_ = connector(hits,size=1,max_pages=1)
    rep = run_scan(ctx.session_factory,partial,ctx.settings,now+timedelta(seconds=10))
    assert rep.incomplete_pages == [PAGE_URL] and rep.seller_events['gone'] == 0
    with ctx.session_factory() as s:
        assert len(list(s.scalars(select(SellerOfferRow).where(SellerOfferRow.active.is_(True))))) == 2


def test_old_provider_notification_is_suppressed_after_scope_change(ctx, now):
    from .test_screener import SimulatedListing
    configure(ctx,now)
    assert run_scan(ctx.session_factory,SimulatedListing(),ctx.settings,now).alerts_enqueued == 1
    ctx.settings.file_config.scope.allowed_source_keys = ['coingate']
    sink = MemorySink()
    rep = dispatch_pending(ctx.session_factory,sink,now,eligibility=delivery_check(ctx.settings))
    assert rep.suppressed == 1 and sink.sent == []
