"""Pagination must broaden discovery without inventing complete inventory or executable quotes."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from value_rail.connectors.aggregators import AggLead, AggPage, CoinGateSearch, BsvPage, parse_bsv_list
from value_rail.net.errors import ParserBroken, UpstreamError
from value_rail.storage.orm import SellerOfferRow, ScanRunRow
from value_rail.worker.scan import run_scan

from .test_aggregators import make, McpReplay, NOW


def search_connector(total=5, budget=4):
    c, _, _ = make('coingate', transport=McpReplay())
    c.config.brands = []
    c.config.searches = [CoinGateSearch(id='search', category='payment-cards', country='DE', per_page=2)]
    c.config.max_search_pages = budget
    calls = []
    def call(tool, args):
        calls.append((tool, args))
        page = args['page']
        entries = [{'brand_slug': f'brand-{i}', 'name': f'Brand {i}'}
                   for i in range((page-1)*2, min(page*2, total))]
        return ({'results': entries, 'total_results': total, 'total_pages': (total+1)//2,
                 'page': page, 'per_page': 2},
                {'_body_sha256': str(page)*64, '_body_bytes': 100, '_status': 200})
    c.call_tool = call
    return c, calls


def test_all_pages_fetched_and_hashed_in_evidence():
    c, calls = search_connector()
    items = c.discovery(NOW)
    assert len(items) == 5 and [args['page'] for _, args in calls] == [1, 2, 3]
    offer = c.normalize(items[-1], c.offer_fetch(items[-1], NOW)[0], NOW)
    proof = offer.evidence[0].payload
    assert proof['enumeration_complete'] is True
    assert [p['body_sha256'] for p in proof['page_proofs']] == [str(i)*64 for i in (1, 2, 3)]
    assert c.ok_pages == c.observed_pages and not c.incomplete_pages
    assert offer.source.role.value == 'discovery_only'


def test_page_budget_retains_leads_but_never_proves_disappearance():
    c, _ = search_connector(budget=2)
    assert len(c.discovery(NOW)) == 4
    assert not c.ok_pages and c.observed_pages == c.incomplete_pages


@pytest.mark.parametrize('fault', ['repeated_page', 'drifting_total', 'duplicate', 'short_page', 'boolean_total', 'down'])
def test_bad_later_page_is_a_disturbance(fault):
    c, _ = search_connector()
    original = c.call_tool
    def call(tool, args):
        sc, msg = original(tool, args)
        if args['page'] == 2:
            if fault == 'down':
                raise UpstreamError('coingate', 'down')
            if fault == 'repeated_page': sc['page'] = 1
            if fault == 'drifting_total': sc['total_results'] = 6
            if fault == 'duplicate': sc['results'][0]['brand_slug'] = 'brand-0'
            if fault == 'short_page': sc['results'] = sc['results'][:1]
            if fault == 'boolean_total': sc['total_results'] = True
        return sc, msg
    c.call_tool = call
    items = c.discovery(NOW)
    assert len(items) == 1 and items[0].meta['page_error']
    assert not c.observed_pages and not c.ok_pages


def test_details_only_use_returned_recognized_brands_and_enforce_budget():
    c, _ = search_connector(total=2)
    c.config.max_discovered_brand_details = 1
    calls = []
    def call(tool, args):
        calls.append((tool, args))
        if tool == 'search_gift_cards':
            sc = {'results': [{'brand_slug': slug, 'name': name} for slug, name in
                             [('aircash-a-bon', 'Aircash A-bon'), ('pcs', 'PCS')]],
                  'page': 1, 'per_page': 2, 'total_results': 2, 'total_pages': 1}
        else:
            sc = {'products': [{'gift_card_id': 17, 'name': 'Aircash A-bon', 'currency': 'EUR',
                               'denominations': [{'value': 10, 'price': 11}]}]}
        return sc, {'_body_sha256': 'a'*64, '_body_bytes': 100, '_status': 200}
    c.call_tool = call
    items = c.discovery(NOW)
    assert [name for name, _ in calls] == ['search_gift_cards', 'get_gift_card']
    expected = ['aircash-a-bon', 'pcs'][NOW.date().toordinal() % 2]
    assert calls[-1][1] == {'brand': expected, 'country': 'DE'}
    detail = items[-1]
    assert detail.product.face_value == Decimal(10)
    assert detail.product.redemption_program == expected
    assert not c.capabilities().checkout_quote and not c.capabilities().exit_quote
    assert any('details_not_fetched=1' in n for page, _ in c._pages.values() for n in page.notes)


@pytest.mark.parametrize('content', ['OnlyFans', 'Chaturbate', 'Discord', 'Midjourney', 'Facebook Ads', 'GoCash Game Card'])
def test_content_brand_is_not_enriched(content):
    c, _ = search_connector(total=1)
    c.config.max_discovered_brand_details = 12
    def call(tool, args):
        assert tool == 'search_gift_cards'
        return ({'results': [{'brand_slug': 'rewarble-' + content.lower().replace(' ', '-'), 'name': 'Rewarble ' + content}],
                 'page': 1, 'per_page': 2, 'total_results': 1, 'total_pages': 1},
                {'_body_sha256': 'a'*64, '_body_bytes': 100, '_status': 200})
    c.call_tool = call
    assert len(c.discovery(NOW)) == 1


def test_partial_page_does_not_mark_previously_observed_seller_gone(ctx):
    c, _ = search_connector()
    t = c.config.searches[0]
    def page(ids, complete):
        return AggPage(t.id, 'https://example.org/list', 200,
                       [AggLead(str(i), 'Aircash 10 EUR', 'seller', Decimal(10), 'EUR', '11', 'EUR')
                        for i in ids], 'a'*64, 10, 'b'*64, complete=complete)
    c.fetch_target = lambda _: page([1, 2], True)
    first = run_scan(ctx.session_factory, c, ctx.settings, NOW)
    assert first.seller_events['baseline'] == 2
    c.fetch_target = lambda _: page([1], False)
    second = run_scan(ctx.session_factory, c, ctx.settings, NOW + timedelta(minutes=1))
    assert second.incomplete_pages == ['https://example.org/list']
    assert second.seller_events['gone'] == 0
    with ctx.session_factory() as s:
        assert len(s.scalars(select(SellerOfferRow).where(SellerOfferRow.active.is_(True))).all()) == 2
        assert 'partial listings' in s.get(ScanRunRow, second.scan_run_id).notes
    c.fetch_target = lambda _: page([1], True)
    third = run_scan(ctx.session_factory, c, ctx.settings, NOW + timedelta(minutes=2))
    assert third.seller_events['gone'] == 1


@pytest.mark.parametrize('pagination,complete', [
    ({'total': 1, 'pageCount': 1}, True),
    ({'total': '1', 'pageCount': '1'}, True),
    ({'total': 3, 'pageCount': 3}, False),
    ({'total': 2, 'pageCount': 1}, False),
    ({'total': 1, 'pageCount': 0}, False),
    ({'total': True, 'pageCount': 1}, False),
    ({}, False),
])
def test_bsv_first_page_requires_proof_of_whole_category(pagination, complete):
    import json
    data = [{'id': 1, 'price': 11, 'currency': 'EUR', 'name': 'Aircash 10 EUR'}]
    flight = '"initialProductsList":' + json.dumps(data) + ',"initialPagination":' + json.dumps(pagination)
    html = ('<script>self.__next_f.push([1,' + json.dumps(flight) + ']);</script>').encode()
    page = parse_bsv_list('bsv', BsvPage(id='x', path='/en/products/list/abon/'),
                          'https://www.buysellvouchers.com/en/products/list/abon/', 200, html)
    assert len(page.leads) == 1 and page.complete is complete


def test_daily_budget_rotates_to_later_returned_brands():
    c, _ = search_connector(total=2)
    c.config.max_discovered_brand_details = 1
    brands = []
    def call(tool, args):
        if tool == 'search_gift_cards':
            sc = {'results': [{'brand_slug': slug, 'name': name} for slug, name in
                             [('aircash-a-bon', 'Aircash A-bon'), ('pcs', 'PCS')]],
                  'page': 1, 'per_page': 2, 'total_results': 2, 'total_pages': 1}
        else:
            brands.append(args['brand'])
            sc = {'products': [{'gift_card_id': 17, 'currency': 'EUR',
                               'denominations': [{'value': 10, 'price': 11}]}]}
        return sc, {'_body_sha256': 'a'*64, '_body_bytes': 100, '_status': 200}
    c.call_tool = call
    c.discovery(NOW)
    c.discovery(NOW + timedelta(days=1))
    assert set(brands) == {'aircash-a-bon', 'pcs'}
