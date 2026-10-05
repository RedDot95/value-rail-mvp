"""Telegram AlertSink: implemented, DISABLED without config, never sends in tests (fake transport)."""

from __future__ import annotations

import json

import pytest

from value_rail.alerts.dispatcher import dispatch_pending
from value_rail.alerts.sinks import (AlertDeliveryError, CompositeSink, LogAlertSink, MemorySink, TelegramAlertSink,
                                     build_sink, build_sink_from_settings)
from value_rail.settings import Settings
from value_rail.storage.orm import AlertRow
from value_rail.worker.scan import run_scan

from .recorded import make_client

TOKEN = "123456:TEST-not-a-real-token"
URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
PAYLOAD = {"event_id": "ev1", "summary_de": "Preisfund: x", "route_key": "r", "status_de": "Preisfund",
           "reason": "new", "route_evaluation_id": 1, "evaluated_at_utc": "2026-10-05T21:00:00+00:00",
           "missing_evidence": ["checkout_quote"], "synthetic": False}


def tg(routes):
    client, transport, _ = make_client(routes, allowed=("api.telegram.org",), respect_robots=False, min_interval=0)
    return TelegramAlertSink(TOKEN, "-100123", client=client), transport


def test_disabled_without_token_and_chat_id(caplog):
    assert isinstance(build_sink("log,telegram", None), LogAlertSink)
    assert isinstance(build_sink("log,telegram", None, telegram_token=TOKEN), LogAlertSink)
    with pytest.raises(ValueError):
        TelegramAlertSink("", "1")
    s = Settings(_env_file=None)
    assert s.telegram_configured is False and isinstance(build_sink_from_settings(s), LogAlertSink)


def test_enabled_only_with_both_and_listed():
    sink = build_sink("log,telegram", None, telegram_token=TOKEN, telegram_chat_id="1")
    assert isinstance(sink, CompositeSink) and sink.name == "log+telegram"
    assert isinstance(build_sink("log", None, telegram_token=TOKEN, telegram_chat_id="1"), LogAlertSink)


def test_send_posts_sendmessage_json():
    sink, transport = tg({URL: (200, {"content-type": "application/json"}, b'{"ok":true,"result":{}}')})
    sink.send(PAYLOAD)
    call = transport.calls[-1]
    assert call["method"] == "POST" and call["url"] == URL
    body = json.loads(call["body"])
    assert body["chat_id"] == "-100123" and "Preisfund: x" in body["text"] and "checkout_quote" in body["text"]


def test_synthetic_skipped_by_default():
    sink, transport = tg({})
    sink.send(PAYLOAD | {"synthetic": True})
    assert transport.calls == [] and sink.skipped == ["ev1"]


@pytest.mark.parametrize("resp", [(429, {}, b""), (401, {}, b""), (200, {}, b'{"ok":false,"description":"bad ' + TOKEN.encode() + b'"}')])
def test_errors_are_sanitised(resp):
    sink, _ = tg({URL: resp})
    with pytest.raises(AlertDeliveryError) as ei:
        sink.send(PAYLOAD)
    assert TOKEN not in str(ei.value) and "123456" not in str(ei.value)
    assert TOKEN not in repr(sink)


def test_composite_does_not_resend_to_successful_sink():
    ok, bad = MemorySink(), MemorySink(fail_times=1)
    ok.name, bad.name = "a", "b"
    comp = CompositeSink([ok, bad])
    with pytest.raises(AlertDeliveryError):
        comp.send(PAYLOAD)
    comp.send(PAYLOAD)
    assert len(ok.sent) == 1 and len(bad.sent) == 1


def test_dispatcher_outbox_never_stores_token(ctx, now):
    from value_rail.connectors.fixture import FixtureConnector
    from .conftest import FIXTURES
    run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    sink, _ = tg({URL: (403, {}, b"")})
    sink.send_synthetic = True  # fixtures are synthetic; force the send path against the fake transport
    rep = dispatch_pending(ctx.session_factory, sink, now)
    assert rep.failed >= 1
    with ctx.session_factory() as s:
        errs = [a.last_error for a in s.query(AlertRow).all() if a.last_error]
    assert errs and all(TOKEN not in e for e in errs)
