"""Only robots-allowed normal page navigation can broaden a category inventory."""
import json
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from value_rail.connectors.aggregators import BsvListConfig, BsvListConnector, BsvPage
from value_rail.net.errors import ParserBroken, RobotsDisallowed, UpstreamError
from value_rail.storage.orm import SellerOfferRow
from value_rail.worker.scan import run_scan

from .recorded import make_client
from .test_aggregators import NOW

ROOT = 'https://www.buysellvouchers.com'
PATH = '/en/products/list/a-bon-gift-cards/'
BASE = ROOT + PATH
ROBOTS = b'User-agent: *\nDisallow: /*?\nAllow: /*?page=\nDisallow: /*/products/buy/\n'


def html_page(total, number, size=2, *, current=None, products=None):
    data = products if products is not None else [
        {'id': i+1, 'price': '11', 'currency': 'EUR', 'name': 'A-bon 10 EUR', 'quantity': '3'}
        for i in range((number-1)*size, min(number*size, total))]
    pagination = {'total': str(total), 'currentPage': number if current is None else current,
                  'pageSize': str(size), 'pageCount': (total+size-1)//size}
    flight = '"initialProductsList":' + json.dumps(data) + ',"initialPagination":' + json.dumps(pagination)
    return ('<script>self.__next_f.push([1,' + json.dumps(flight) + ']);</script>').encode()


def connector(total=5, *, per_category=4, extra=12, robots=ROBOTS):
    routes = {ROOT+'/robots.txt': (200, {'content-type': 'text/plain'}, robots)}
    for number in range(1, max(1, (total+1)//2)+1):
        url = BASE if number == 1 else BASE + f'?page={number}'
        routes[url] = (200, {'content-type': 'text/html'}, html_page(total, number))
    client, transport, clock = make_client(routes, allowed=('www.buysellvouchers.com',), retries=0)
    config = BsvListConfig(source_key='bsv', source_name='BSV test',
                          pages=[BsvPage(id='abon', path=PATH, family='abon', redemption_program='abon', empty_ok=True)],
                          max_pages_per_category=per_category, max_additional_pages=extra)
    return BsvListConnector(config, client=client), transport, clock


def test_complete_inventory_preserves_page_proofs_and_original_lead_url():
    c, transport, clock = connector()
    items = c.discovery(NOW)
    assert len(items) == 5 and c.ok_pages == {BASE} and not c.incomplete_pages
    offer = c.normalize(items[-1], c.offer_fetch(items[-1], NOW)[0], NOW)
    evidence = offer.evidence[0].payload
    assert evidence['enumeration_complete'] is True
    assert {p['page'] for p in evidence['page_proofs']} == {1, 2, 3}
    assert all(len(p['body_sha256']) == 64 for p in evidence['page_proofs'])
    assert evidence['lead']['raw']['listing_page_url'] == BASE + '?page=3'
    assert offer.raw['seller_offer']['page_url'] == BASE  # stable category inventory key
    assert offer.source.role.value == 'discovery_only' and not c.capabilities().checkout_quote
    assert all(s >= 5 for s in clock.sleeps)
    assert all(call['method'] == 'GET' for call in transport.calls)


def test_daily_windows_rotate_and_never_claim_complete():
    c, _, _ = connector(total=12, per_category=2, extra=1)
    pages = []
    for day in range(5):
        assert len(c.discovery(NOW + timedelta(days=day))) == 4
        observed, _ = c._pages['abon']
        assert observed.complete is False and c.incomplete_pages == {BASE} and not c.ok_pages
        pages.append(observed.page_proofs[-1]['page'])
    assert set(pages) == {2, 3, 4, 5, 6}


def test_source_wide_budget_applies_across_categories_and_resets_each_scan():
    c, tr, _ = connector(total=6, per_category=3, extra=1)
    other = '/en/products/list/pcs-gift-cards/'
    c.config.pages.append(BsvPage(id='pcs', path=other, family='pcs', redemption_program='pcs'))
    for number in (1, 2, 3):
        url = ROOT+other if number == 1 else ROOT+other+f'?page={number}'
        tr.routes[url] = (200, {'content-type': 'text/html'}, html_page(6, number))
    priority = []
    for day in range(2):
        before = len(tr.calls)
        c.discovery(NOW + timedelta(days=day))
        requests = [call['url'] for call in tr.calls[before:] if '?page=' in call['url']]
        assert len(requests) == 1
        priority.append(requests[0].split('?')[0])
    assert set(priority) == {BASE, ROOT+other}


def test_robots_can_revoke_pagination_without_query_request():
    c, tr, _ = connector(robots=b'User-agent: *\nDisallow: /*?\n')
    items = c.discovery(NOW)
    assert len(items) == 1 and items[0].meta['page_error']
    with pytest.raises(RobotsDisallowed):
        c.offer_fetch(items[0], NOW)
    assert not c.ok_pages and not any('?page=' in call['url'] for call in tr.calls)


@pytest.mark.parametrize('fault', ['repeated', 'short', 'drifting', 'duplicate', 'down', 'boolean'])
def test_invalid_later_page_is_not_zero_offers_or_complete_inventory(fault):
    c, tr, _ = connector()
    url = BASE + '?page=2'
    if fault == 'down':
        tr.routes[url] = (503, {'content-type': 'text/html'}, b'down')
    else:
        body = html_page(5, 2)
        if fault == 'repeated': body = html_page(5, 2, current=1)
        if fault == 'short': body = html_page(5, 2, products=[{'id': 3, 'price': 11, 'currency': 'EUR'}])
        if fault == 'drifting': body = html_page(6, 2)
        if fault == 'duplicate': body = html_page(5, 2, products=[{'id': 1, 'price': 11, 'currency': 'EUR'},
                                                                  {'id': 4, 'price': 11, 'currency': 'EUR'}])
        if fault == 'boolean': body = body.replace(b'\\"currentPage\\": 2', b'\\"currentPage\\": true')
        tr.routes[url] = (200, {'content-type': 'text/html'}, body)
    items = c.discovery(NOW)
    assert len(items) == 1 and items[0].meta['page_error']
    with pytest.raises((ParserBroken, UpstreamError)):
        c.offer_fetch(items[0], NOW)
    assert not c.observed_pages and not c.ok_pages


def test_missing_metadata_stays_partial_without_requesting_guessed_pages():
    c, tr, _ = connector()
    body = html_page(5, 1).replace(b'\\"pageSize\\": \\"2\\", ', b'')
    tr.routes[BASE] = (200, {'content-type': 'text/html'}, body)
    assert len(c.discovery(NOW)) == 2
    assert c.incomplete_pages == {BASE}
    assert not any('?page=' in call['url'] for call in tr.calls)


def test_valid_explicitly_empty_category_is_complete():
    c, _, _ = connector(total=0)
    assert c.discovery(NOW) == []
    assert c.ok_pages == {BASE} and not c.incomplete_pages


@pytest.mark.parametrize('path', [PATH+'?page=2', PATH+'?pageSize=100', PATH+'#fragment',
                                  '/en/products/list/../buy/', '/en/products/list/x/../../cart/',
                                  '/en/products/list//x/'])
def test_config_accepts_only_category_root_not_arbitrary_navigation(path):
    with pytest.raises(ValidationError):
        BsvPage(path=path)


def test_partial_daily_window_never_marks_unseen_seller_gone(ctx):
    c, _, _ = connector(total=8, per_category=2, extra=1)
    first = run_scan(ctx.session_factory, c, ctx.settings, NOW)
    assert first.offers_seen == 4
    second = run_scan(ctx.session_factory, c, ctx.settings, NOW + timedelta(days=1))
    assert second.offers_seen == 4 and second.seller_events['gone'] == 0
    with ctx.session_factory() as s:
        assert len(s.scalars(select(SellerOfferRow).where(SellerOfferRow.active.is_(True))).all()) == 6
