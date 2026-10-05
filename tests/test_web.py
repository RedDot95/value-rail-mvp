from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from value_rail.connectors.fixture import FixtureConnector
from value_rail.domain.timeutil import utcnow
from value_rail.services import AppContext
from value_rail.web.app import create_app
from value_rail.worker.scan import run_scan

from .conftest import FIXTURES, make_settings


def _client(ctx):
    run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, utcnow())
    return TestClient(create_app(ctx))


def test_dashboard_mobile_html(ctx):
    c = _client(ctx)
    r = c.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'name="viewport"' in html
    assert "SYNTHETISCHE TESTDATEN" in html and "SYNTHETIC" in html
    assert "Preisfunde (2)" in html and "Verifizierte Routen (3)" in html
    assert "76,00 %" in html and "55,00 €" in html and "122,22 %" in html
    assert "Systemstatus" in html


def test_detail_shows_breakdown_and_evidence(ctx):
    c = _client(ctx)
    evs = c.get("/api/evaluations").json()
    r04 = next(e for e in evs if e["route_key"].endswith("R04_verified_profit_55"))
    html = c.get(f"/evaluations/{r04['id']}").text
    assert "Kostenaufstellung" in html and "Evidenz" in html and "checkout_quote" in html
    assert c.get(f"/evaluations/{r04['id']}/replay").json()["match"] is True
    assert c.get("/evaluations/99999").status_code == 404


def test_status_page_and_health(ctx):
    c = _client(ctx)
    assert "Live-Connector: <b>aus (nur manueller Smoke-Test)</b>" in c.get("/status").text
    h = c.get("/healthz").json()
    assert h["live_scanning"] is False and h["telegram_configured"] is False
    assert c.get("/livez").status_code == 200


def test_basic_auth_enforced_when_configured(tmp_path):
    ctx = AppContext(make_settings(tmp_path, basic_user="u", basic_password="secret"))
    ctx.init_db()
    c = TestClient(create_app(ctx))
    assert c.get("/").status_code == 401
    assert c.get("/healthz").status_code == 200
    tok = base64.b64encode(b"u:secret").decode()
    assert c.get("/", headers={"Authorization": f"Basic {tok}"}).status_code == 200
    bad = base64.b64encode(b"u:wrong").decode()
    assert c.get("/", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    ctx.dispose()
