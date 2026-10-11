"""Persisted public signal feed used by the ChatGPT hourly reader."""
import json
from datetime import timedelta
from value_rail.clearance_feed import export_feed
from .test_coingate_clearance import connector, code, KEY
from .test_screener import configure


def test_feed_ids_survive_no_change_and_outage_but_change_on_price_and_return(ctx, now):
    configure(ctx,now)
    c,state,_ = connector([code(now)])
    def read(previous=None,offset=0):
        return export_feed(ctx.settings,previous,now=now+timedelta(seconds=offset),connector=c)
    first=read()
    row=first['offers'][0]
    assert first['status']=='ok' and row['quantity']==1 and row['discount']=='0.2'
    second=read(first,10)
    assert second['offers'][0]['signal_id']==row['signal_id']
    assert KEY not in json.dumps(first) and 'code_ids' not in json.dumps(first)
    state['hits'][0]['price']=7
    cheaper=read(second,20)
    assert cheaper['offers'][0]['signal_id']!=row['signal_id']
    assert cheaper['offers'][0]['reason']=='material_price_change'
    state['hits'][0]['provider']='regular'
    failed=read(cheaper,30)
    assert failed['status']=='error' and failed['offers']==cheaper['offers']
    state['hits'][0]['provider']='resale'
    restored=read(failed,40)
    assert restored['offers'][0]['signal_id']==cheaper['offers'][0]['signal_id']
    state['hits']=[]
    empty=read(restored,50)
    assert empty['status']=='ok' and empty['offers']==[]
    state['hits']=[code(now,price=7)]
    returned=read(empty,60)
    assert returned['offers'][0]['signal_id']!=cheaper['offers'][0]['signal_id']
    state['hits']=[]
    gone_again=read(returned,70)
    state['hits']=[code(now,price=7)]
    returned_again=read(gone_again,80)
    assert returned_again['offers'][0]['signal_id']!=returned['offers'][0]['signal_id']


def test_partial_scan_preserves_previous_state_without_claiming_freshness(ctx,now):
    configure(ctx,now)
    c,_,_=connector([code(now)])
    previous=export_feed(ctx.settings,now=now,connector=c)
    partial,_,_=connector([code(now),code(now,'2')],size=1,max_pages=1)
    report=export_feed(ctx.settings,previous,now=now+timedelta(seconds=10),connector=partial)
    assert report['status']=='error' and not report['enumeration_complete']
    assert report['last_success_at']==previous['last_success_at'] and report['offers']==previous['offers']


def test_expired_and_below_threshold_codes_do_not_enter_feed(ctx,now):
    configure(ctx,now)
    c,_,_=connector([code(now,price=10),code(now,'2',expires_at=1)])
    report=export_feed(ctx.settings,now=now,connector=c)
    assert report['status']=='ok' and report['total_candidates']==0
