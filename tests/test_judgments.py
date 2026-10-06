"""Enrichment/safety layer (TypeSafe judgments, docs/decisions.md D-42). Offline: no network, no API key."""

from __future__ import annotations

import ast
import json
import random
import re
import socket
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from typer.testing import CliRunner

from value_rail.cli import app
from value_rail.connectors.fixture import FixtureConnector
from value_rail.judgments.base import JudgmentKind, JudgmentRequest, JudgmentResult, Question
from value_rail.judgments.null_provider import NullJudgmentProvider
from value_rail.judgments.questions import (CLASSIFY_INSTRUMENT, LOOKS_LIKE_BLOCK_PAGE, NONE_OPTION, RESTRICTION_RISK,
                                            SELECT_FACE_VALUE, extract_numeric_candidates,
                                            resolve_selected_candidate, select_face_value)
from value_rail.judgments.safety import advisory_status, advisory_view
from value_rail.judgments.service import EnrichmentService, OfferContext, build_enrichment_service, build_provider
from value_rail.judgments.typesafe_provider import TypeSafeJudgmentProvider
from value_rail.net import http_safe
from value_rail.net.http_safe import PolitenessPolicy, SafeHttpClient, TransportResponse
from value_rail.services import AppContext
from value_rail.settings import EnrichmentConfig, Settings
from value_rail.storage.orm import OfferJudgmentRow, RouteEvaluationRow
from value_rail.worker.scan import run_scan

from .conftest import FIXTURES, NOW, REPO, make_settings

FAKE_KEY = "ts-test-NOT-A-REAL-KEY-0123456789"
SRC = REPO / "src" / "value_rail"


# ---------------------------------------------------------------- fakes / helpers

class FakeJudgmentProvider:
    """Canned distributions per question id. Records every request; never touches the network."""

    name = "fake"

    def __init__(self, canned: dict[str, dict] | None = None) -> None:
        self.canned = canned or {}
        self.requests: list[JudgmentRequest] = []

    def judge(self, request: JudgmentRequest) -> list[JudgmentResult]:
        self.requests.append(request)
        out = []
        for q in request.questions:
            c = self.canned.get(q.id)
            if c is None:
                out.append(JudgmentResult(question_id=q.id, kind=q.kind, provider=self.name, model="fake-1",
                                          created_at=NOW, abstained=True, abstain_reason="no canned answer"))
                continue
            c = c(q) if callable(c) else c
            out.append(JudgmentResult(question_id=q.id, kind=q.kind, provider=self.name, model="fake-1",
                                      created_at=NOW, **c))
        return out


def noul(p: float) -> dict:
    return {"answer": "yes" if p >= 0.5 else "no", "probability": p}


def choice(option: str, conf: float = 0.95) -> dict:
    return {"answer": option, "probability": conf, "confidence": conf, "distribution": {option: conf}}


HIGH_RISK = {RESTRICTION_RISK: noul(0.95), LOOKS_LIKE_BLOCK_PAGE: noul(0.97),
             CLASSIFY_INSTRUMENT: choice("crypto_voucher"), SELECT_FACE_VALUE: lambda q: choice(q.options[0])}


def enabled_cfg(**kw) -> EnrichmentConfig:
    return EnrichmentConfig(enabled=True, **kw)


def fresh_ctx(tmp_path: Path, name: str) -> AppContext:
    d = tmp_path / name
    d.mkdir()
    c = AppContext(make_settings(d))
    c.settings.alert_log_file = str(d / "alerts.log")
    c.init_db(now=NOW)
    return c


def db_dump(c: AppContext) -> dict[str, list]:
    """Raw stored bytes of everything the deterministic path produces."""
    with c.engine.connect() as conn:
        ev = conn.execute(text("SELECT id, route_key, status, discount, profit_eur, edge, evaluated_quantity, inputs, "
                               "outputs, inputs_hash, engine_version FROM route_evaluations ORDER BY id")).all()
        al = conn.execute(text("SELECT id, event_id, route_key, route_evaluation_id, state, reason, payload "
                               "FROM alerts ORDER BY id")).all()
        snaps = conn.execute(text("SELECT id, price_amount, price_currency, raw, content_hash FROM offer_snapshots "
                                  "ORDER BY id")).all()
        prods = conn.execute(text("SELECT id, identity_key, face_value, product_family FROM products ORDER BY id")).all()
    return {"evaluations": [tuple(r) for r in ev], "alerts": [tuple(r) for r in al],
            "snapshots": [tuple(r) for r in snaps], "products": [tuple(r) for r in prods]}


class CountingFixtureConnector(FixtureConnector):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = {"discovery": 0, "offer_fetch": 0, "checkout_quote": 0, "exit_quote": 0}

    def discovery(self, now):
        self.calls["discovery"] += 1
        return super().discovery(now)

    def offer_fetch(self, item, now):
        self.calls["offer_fetch"] += 1
        return super().offer_fetch(item, now)

    def checkout_quote(self, item, now):
        self.calls["checkout_quote"] += 1
        return super().checkout_quote(item, now)

    def exit_quote(self, item, now):
        self.calls["exit_quote"] += 1
        return super().exit_quote(item, now)


@pytest.fixture
def no_network(monkeypatch):
    """Any attempt to build an HTTP client or open a socket fails the test."""
    def boom(*a, **kw):
        raise AssertionError("network object constructed")
    monkeypatch.setattr(http_safe.SafeHttpClient, "__init__", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)


# ---------------------------------------------------------------- 1. critical: valuation byte-for-byte unchanged

@pytest.mark.parametrize("provider_kind", ["null", "fake_high_risk"])
def test_valuation_byte_for_byte_unchanged_with_enrichment(tmp_path, provider_kind, no_network):
    base = fresh_ctx(tmp_path, "baseline")
    enr = fresh_ctx(tmp_path, "enriched")
    try:
        rep_a = run_scan(base.session_factory, FixtureConnector(FIXTURES), base.settings, NOW)
        provider = NullJudgmentProvider() if provider_kind == "null" else FakeJudgmentProvider(HIGH_RISK)
        svc = EnrichmentService(provider, enabled_cfg(persist_abstentions=True))
        rep_b = run_scan(enr.session_factory, FixtureConnector(FIXTURES), enr.settings, NOW, enricher=svc)
        assert rep_a.model_dump() == rep_b.model_dump()
        a, b = db_dump(base), db_dump(enr)
        assert a == b  # route_evaluations (incl. canonical inputs/outputs TEXT), alerts, snapshots, products
        assert len(a["evaluations"]) == 10 and len(a["alerts"]) == 5
        with enr.session_factory() as s:
            n = s.scalar(select(func.count()).select_from(OfferJudgmentRow))
            assert n > 0  # enrichment did run - and still changed nothing deterministic
            if provider_kind == "null":
                assert all(j.abstained and j.signal == "abstain" for j in s.scalars(select(OfferJudgmentRow)))
    finally:
        base.dispose()
        enr.dispose()


def test_judgments_package_cannot_reach_money_math_or_alerts():
    """Static guard: the judgments layer imports neither the valuation engine nor alerts/worker/connectors I/O,
    and the valuation/alerts packages never import judgments."""
    forbidden_from_judgments = ("alerts", "valuation", "worker", "connectors.recharge", "connectors.jsonld_shop",
                                "connectors.aggregators")
    for f in (SRC / "judgments").glob("*.py"):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                assert not any(mod == x or mod.startswith(x + ".") or mod.endswith("." + x) for x in
                               forbidden_from_judgments), f"{f.name} imports {mod}"
    for pkg in ("valuation", "alerts"):
        for f in (SRC / pkg).glob("*.py"):
            assert "judgments" not in f.read_text(), f"{pkg}/{f.name} references judgments"


# ---------------------------------------------------------------- 2. select, don't generate

def test_candidate_extraction_is_code_side_and_conservative():
    cands = extract_numeric_candidates([("offer.title", "Bitsa-Familie: Nennwert 5 EUR, all-in 1,20 EUR"),
                                        ("offer.price_text", "$25")])
    assert [(c.text, c.value, c.currency) for c in cands] == [("5 EUR", Decimal("5"), "EUR"),
                                                              ("1,20 EUR", Decimal("1.20"), "EUR"),
                                                              ("$25", Decimal("25"), "unknown")]
    q = select_face_value(cands)
    assert q.kind == JudgmentKind.CHOICE and set(q.options) == {"candidate_0", "candidate_1", "candidate_2", NONE_OPTION}
    # option keys are indices, never the numbers themselves: the model can only point at a code-made candidate
    assert all(k == NONE_OPTION or re.fullmatch(r"candidate_\d+", k) for k in q.options)


def test_select_face_value_only_ever_returns_a_provided_candidate():
    cands = extract_numeric_candidates([("offer.title", "paysafecard 50 EUR for 46,90 € (3 left)")])
    values = {id(c.value) for c in cands}
    rng = random.Random(42)
    answers = [c.option_key for c in cands] + [NONE_OPTION, "candidate_99", "50", "46.90", "50.00 EUR", "", "-1",
                                               "candidate_-1", "CANDIDATE_0", "candidate_0 ", "1e9"]
    answers += ["".join(rng.choice("candidate_0123456789.,€ ") for _ in range(rng.randint(0, 14))) for _ in range(300)]
    for ans in answers:
        for conf in (0.0, 0.5, 0.99, 1.0):
            r = JudgmentResult(question_id=SELECT_FACE_VALUE, kind=JudgmentKind.CHOICE, answer=ans, confidence=conf,
                               probability=conf, provider="fake", model="fake", created_at=NOW)
            picked = resolve_selected_candidate(r, cands, min_confidence=0.8)
            if picked is not None:
                assert picked in cands and id(picked.value) in values  # the very Decimal object code extracted
                assert ans == picked.option_key and conf >= 0.8
    # abstain / wrong kind -> None
    r = JudgmentResult(question_id=SELECT_FACE_VALUE, kind=JudgmentKind.CHOICE, provider="n", model="n",
                       created_at=NOW, abstained=True)
    assert resolve_selected_candidate(r, cands, min_confidence=0.0) is None


def test_face_value_selection_end_to_end_copies_extracted_decimal(ctx, now):
    fake = FakeJudgmentProvider({SELECT_FACE_VALUE: lambda q: choice(q.options[0], 0.97)})
    svc = EnrichmentService(fake, enabled_cfg())
    run_scan(ctx.session_factory, FixtureConnector(FIXTURES, only={"R02_bitsa_price_find"}), ctx.settings, now,
             enricher=svc)
    sent = fake.requests[0]
    assert set(sent.state["numeric_candidates"]) == {"candidate_0", "candidate_1"}
    with ctx.session_factory() as s:
        row = s.scalar(select(OfferJudgmentRow).where(OfferJudgmentRow.question_id == SELECT_FACE_VALUE))
        assert row.selected_value == Decimal("5") and row.selected_candidate["text"] == "5 EUR"
        assert row.signal == "face_value_consistent"  # observed face value (5) is compared, never overwritten


def test_typesafe_choice_outside_options_is_rejected():
    q = select_face_value(extract_numeric_candidates([("t", "10 EUR")]))
    prov = TypeSafeJudgmentProvider(api_key=FAKE_KEY, http_factory=lambda: _client(_reply({
        "model": "jev-1.13.0", "answers": {q.id: {"type": "choice", "choice": "12.50", "confidence": 1.0,
                                                  "probabilities": {"12.50": 1.0}}}})))
    (r,) = prov.judge(JudgmentRequest(state="x", questions=(q,)))
    assert r.abstained and "outside" in r.abstain_reason


# ---------------------------------------------------------------- 3. restriction risk -> blocked path, never an attempt

def test_restriction_risk_high_pushes_to_blocked_without_any_attempt(tmp_path, no_network):
    base = fresh_ctx(tmp_path, "base")
    enr = fresh_ctx(tmp_path, "enr")
    try:
        ca, cb = CountingFixtureConnector(FIXTURES), CountingFixtureConnector(FIXTURES)
        run_scan(base.session_factory, ca, base.settings, NOW)
        fake = FakeJudgmentProvider({RESTRICTION_RISK: noul(0.93)})
        run_scan(enr.session_factory, cb, enr.settings, NOW, enricher=EnrichmentService(fake, enabled_cfg()))
        assert ca.calls == cb.calls  # no extra fetch / retry / alternative route attempted
        assert db_dump(base)["alerts"] == db_dump(enr)["alerts"]  # no alert added, none removed
        with enr.session_factory() as s:
            rows = list(s.scalars(select(OfferJudgmentRow).where(OfferJudgmentRow.question_id == RESTRICTION_RISK)))
            assert rows and all(r.signal == "advisory_block" for r in rows)
            ev = s.scalar(select(RouteEvaluationRow).where(RouteEvaluationRow.route_key == "synthetic:R04_verified_profit_55"))
            assert ev.status == "verified_route"  # deterministic record untouched
            sigs = [r.signal for r in rows if r.route_evaluation_id == ev.id]
            assert advisory_status(ev.status, sigs) == "blocked"
            assert advisory_view(ev.status, sigs)["inferred_block"] is True
    finally:
        base.dispose()
        enr.dispose()


def test_overlay_is_monotone_never_unlocks():
    for st in ("price_find", "verified_route", "blocked", "expired", "no_signal"):
        assert advisory_status(st, ["advisory_block"]) == "blocked"
        assert advisory_status(st, ["no_restriction", "family_consistent", "face_value_selected"]) == st
    assert advisory_status("blocked", []) == "blocked"


def test_restriction_thresholds_are_in_code():
    svc = EnrichmentService(FakeJudgmentProvider({RESTRICTION_RISK: noul(0.6)}), enabled_cfg())
    out = svc.enrich(OfferContext(route_key="r", source_key="s", title="Steam card USD - US only"))
    assert out.signals[RESTRICTION_RISK] == "review_restriction" and not out.advisory_block


# ---------------------------------------------------------------- 4. provider abstains on API error / timeout

def _client(transport, **kw) -> SafeHttpClient:
    return SafeHttpClient(source_key="typesafe-api", allowed_hosts={"api.typesafe.ai"}, respect_robots=False,
                          transport=transport, resolver=lambda h, p: ["104.18.32.7"], sleep=lambda s: None,
                          policy=PolitenessPolicy(min_interval_s=0, jitter_s=0, max_retries=1, backoff_base_s=0), **kw)


def _reply(body, status=200, headers=None):
    calls = []

    def transport(*, method, url, ip, headers: dict, body: bytes | None, timeout, max_bytes):
        calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        payload = body_ if isinstance((body_ := reply_body), bytes) else json.dumps(body_).encode()
        return TransportResponse(status=status, headers=hdrs, body=payload)
    reply_body, hdrs = body, headers or {"content-type": "application/json"}
    transport.calls = calls
    return transport


def _req() -> JudgmentRequest:
    from value_rail.judgments.questions import classify_instrument, looks_like_block_page, restriction_risk
    return JudgmentRequest(state={"offer": {"title": "paysafecard 10 EUR"}},
                           questions=(restriction_risk(), looks_like_block_page(), classify_instrument()))


def _raise(exc):
    def transport(**kw):
        raise exc
    return transport


@pytest.mark.parametrize("transport", [
    _raise(socket.timeout("timed out")), _raise(ConnectionResetError("reset")), _raise(OSError("unreachable")),
    _reply({"error": "x"}, status=500), _reply({"error": "x"}, status=529), _reply({"detail": "bad"}, status=422),
    _reply({"error": "x"}, status=401), _reply({"error": "x"}, status=429), _reply({"error": "x"}, status=403),
    _reply(b"<html>not json</html>"), _reply({"no_answers": True}), _reply([1, 2, 3]),
    _reply({}, status=302, headers={"location": "https://evil.example/steal"}),
], ids=["timeout", "reset", "oserror", "500", "529", "422", "401", "429", "403", "html", "no-answers", "list",
        "redirect"])
def test_typesafe_provider_abstains_never_raises(transport, caplog):
    prov = TypeSafeJudgmentProvider(api_key=FAKE_KEY, http_factory=lambda: _client(transport))
    results = prov.judge(_req())
    assert [r.question_id for r in results] == [RESTRICTION_RISK, LOOKS_LIKE_BLOCK_PAGE, CLASSIFY_INSTRUMENT]
    assert all(r.abstained and r.provider == "typesafe" for r in results)
    assert FAKE_KEY not in caplog.text and all(FAKE_KEY not in r.abstain_reason for r in results)
    assert "abstaining" in caplog.text
    if getattr(transport, "calls", None) is not None and transport.calls and transport.calls[0]["url"]:
        assert all(c["url"] == "https://api.typesafe.ai/v1/systemone" for c in transport.calls)  # never followed


def test_typesafe_provider_request_and_response_shape(caplog):
    t = _reply({"model": "jev-1.13.0", "usage": {"input_tokens": 300, "output_tokens": 20}, "answers": {
        RESTRICTION_RISK: {"type": "noul", "noul": 0.12},
        LOOKS_LIKE_BLOCK_PAGE: {"type": "noul", "noul": 1.7},  # out of range -> abstain for this question only
        CLASSIFY_INSTRUMENT: {"type": "choice", "choice": "paysafecard", "confidence": 0.9,
                              "probabilities": {"paysafecard": 0.94, "bitsa": 0.03, "crypto_voucher": 0.01,
                                                "other_or_none": 0.02}}}})
    prov = TypeSafeJudgmentProvider(api_key=FAKE_KEY, http_factory=lambda: _client(t))
    rr, bp, ci = prov.judge(_req())
    call = t.calls[0]
    assert call["method"] == "POST" and call["url"] == "https://api.typesafe.ai/v1/systemone"
    assert call["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert call["headers"]["Content-Type"] == "application/json"
    sent = json.loads(call["body"])
    assert set(sent) == {"state", "model", "questions"} and sent["model"] == "jev-latest"
    assert sent["questions"][RESTRICTION_RISK]["type"] == "noul"
    assert sent["questions"][CLASSIFY_INSTRUMENT]["type"] == "choice"
    assert set(sent["questions"][CLASSIFY_INSTRUMENT]["criteria"]) == {"bitsa", "paysafecard", "crypto_voucher",
                                                                      "other_or_none"}
    assert not rr.abstained and rr.probability == 0.12 and rr.answer == "no" and rr.model == "jev-1.13.0"
    assert bp.abstained and "probability" in bp.abstain_reason
    assert ci.answer == "paysafecard" and ci.confidence == 0.9 and ci.probability == 0.94
    assert FAKE_KEY not in repr(prov) and FAKE_KEY not in caplog.text


def test_authorized_post_refuses_bad_tokens_and_http():
    c = _client(_reply({}))
    for bad in ("", "a b", "x\r\nX-Evil: 1", "tökén"):
        with pytest.raises(ValueError):
            c.post_json_authorized("https://api.typesafe.ai/v1/systemone", b"{}", bearer_token=bad)
    from value_rail.net.errors import BlockedUrl
    with pytest.raises(BlockedUrl):
        c.post_json_authorized("http://api.typesafe.ai/v1/systemone", b"{}", bearer_token=FAKE_KEY)
    with pytest.raises(BlockedUrl):  # host allowlist still applies
        c.post_json_authorized("https://other.example/v1/systemone", b"{}", bearer_token=FAKE_KEY)


def test_service_survives_a_raising_provider():
    class Raiser:
        name = "raiser"

        def judge(self, request):
            raise RuntimeError("boom")
    out = EnrichmentService(Raiser(), enabled_cfg()).enrich(OfferContext(route_key="r", source_key="s", title="x"))
    assert out is not None and all(r.abstained for r in out.results)


# ---------------------------------------------------------------- 5. off by default

def test_off_by_default_constructs_nothing_and_scan_is_identical(tmp_path, monkeypatch, no_network):
    import value_rail.judgments.service as service_mod
    import value_rail.judgments.typesafe_provider as tp

    def boom(*a, **kw):
        raise AssertionError("enrichment touched while disabled")
    monkeypatch.setattr(service_mod, "build_enrichment_service", boom)
    monkeypatch.setattr(tp.TypeSafeJudgmentProvider, "__init__", boom)
    monkeypatch.setenv("TYPESAFE_API_KEY", FAKE_KEY)  # even with a key present, disabled means disabled
    a, b = fresh_ctx(tmp_path, "a"), fresh_ctx(tmp_path, "b")
    try:
        assert a.settings.file_config.enrichment.enabled is False
        assert a.settings.file_config.enrichment.provider == "null"
        assert a.settings.enrichment_provider_effective == "null"
        ra = run_scan(a.session_factory, FixtureConnector(FIXTURES), a.settings, NOW)
        rb = run_scan(b.session_factory, FixtureConnector(FIXTURES), b.settings, NOW)
        assert ra.model_dump() == rb.model_dump() and db_dump(a) == db_dump(b)
        with a.session_factory() as s:
            assert s.scalar(select(func.count()).select_from(OfferJudgmentRow)) == 0
    finally:
        a.dispose()
        b.dispose()


def _settings_with(tmp_path, monkeypatch, *, enabled, provider, key):
    if key:
        monkeypatch.setenv("TYPESAFE_API_KEY", key)
    else:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.delenv("VALUE_RAIL_TYPESAFE_API_KEY", raising=False)
    s = make_settings(tmp_path)
    s.file_config.enrichment.enabled = enabled
    s.file_config.enrichment.provider = provider
    return s


def test_provider_resolution(tmp_path, monkeypatch, no_network):
    s = _settings_with(tmp_path, monkeypatch, enabled=False, provider="typesafe", key=FAKE_KEY)
    assert build_enrichment_service(s) is None and isinstance(build_provider(s), NullJudgmentProvider)
    s = _settings_with(tmp_path, monkeypatch, enabled=True, provider="typesafe", key="")
    assert isinstance(build_provider(s), NullJudgmentProvider) and s.enrichment_provider_effective == "null"
    s = _settings_with(tmp_path, monkeypatch, enabled=True, provider="null", key=FAKE_KEY)
    assert isinstance(build_provider(s), NullJudgmentProvider)
    s = _settings_with(tmp_path, monkeypatch, enabled=True, provider="typesafe", key=FAKE_KEY)
    p = build_provider(s)  # constructed, but lazily: no SafeHttpClient yet (no_network would raise)
    assert isinstance(p, TypeSafeJudgmentProvider) and s.enrichment_provider_effective == "typesafe"
    assert FAKE_KEY not in repr(s.typesafe_api_key) and FAKE_KEY not in repr(p)


# ---------------------------------------------------------------- 6. budget / caps / storage / UI / CLI

def test_budget_and_question_cap():
    fake = FakeJudgmentProvider({RESTRICTION_RISK: noul(0.1)})
    svc = EnrichmentService(fake, enabled_cfg(max_requests_per_scan=2, max_questions_per_offer=1))
    ctxs = [OfferContext(route_key=f"r{i}", source_key="s", title="Bitsa 10 EUR", payload="{}") for i in range(5)]
    rep, outs = svc.run(ctxs)
    assert rep.requests == 2 and rep.skipped_budget == 3 and len(fake.requests) == 2
    assert all([q.id for q in r.questions] == [RESTRICTION_RISK] for r in fake.requests)  # safety question first
    svc0 = EnrichmentService(fake, enabled_cfg(max_questions_per_offer=0))
    assert svc0.run(ctxs)[0].requests == 0


def test_judgments_are_append_only(ctx, now):
    svc = EnrichmentService(FakeJudgmentProvider({RESTRICTION_RISK: noul(0.2)}), enabled_cfg())
    run_scan(ctx.session_factory, FixtureConnector(FIXTURES, only={"R03_paysafe_partial_qty"}), ctx.settings, now,
             enricher=svc)
    from value_rail.storage.orm import ImmutableRecordError
    with pytest.raises(ImmutableRecordError):
        with ctx.session_factory.begin() as s:
            s.scalars(select(OfferJudgmentRow)).first().probability = 0.99
    with pytest.raises(Exception, match="immutable"):
        with ctx.engine.begin() as conn:
            conn.execute(text("DELETE FROM offer_judgments"))


def test_detail_page_shows_inferred_card_only_when_enabled(ctx, now):
    from starlette.testclient import TestClient

    from value_rail.web.app import create_app
    svc = EnrichmentService(FakeJudgmentProvider(HIGH_RISK), enabled_cfg())
    rep = run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now, enricher=svc)
    ev_id = rep.evaluation_ids["synthetic:R04_verified_profit_55"]
    client = TestClient(create_app(ctx))
    off = client.get(f"/evaluations/{ev_id}").text
    assert "Inferred (Modell)" not in off
    ctx.settings.file_config.enrichment.enabled = True
    on = client.get(f"/evaluations/{ev_id}").text
    assert "Inferred (Modell)" in on and "Blockiert (inferred)" in on and "advisory_block" in on
    assert "Verifizierte Route" in on  # deterministic status still shown as is


def test_cli_enrich_dry_run_offline(tmp_path, monkeypatch, no_network):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    env = {"VALUE_RAIL_DB_PATH": str(tmp_path / "cli.db"), "VALUE_RAIL_FIXTURES_DIR": str(FIXTURES),
           "VALUE_RAIL_CONFIG_PATH": str(REPO / "config" / "default.toml"),
           "VALUE_RAIL_MIGRATIONS_DIR": str(REPO / "migrations"), "VALUE_RAIL_DB_URL": ""}
    res = CliRunner().invoke(app, ["enrich", "--dry-run"], env=env)
    assert res.exit_code == 0, res.output
    assert "provider=null" in res.output and "DRY-RUN" in res.output and "signal=abstain" in res.output
    assert "synthetic:block-page-sample" in res.output and "candidate_0='5 EUR'" in res.output
    last = json.loads(res.output.strip().splitlines()[-1])
    assert last["provider"] == "null" and last["judgments_persisted"] == 0 and last["requests"] == 12  # 11 fixture offers + 1 block-page sample
    assert not (tmp_path / "cli.db").exists()  # dry-run writes nothing
    # without --dry-run and disabled -> refuses
    assert CliRunner().invoke(app, ["enrich"], env=env).exit_code == 2


def test_diagnose_never_prints_the_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = {"VALUE_RAIL_DB_PATH": str(tmp_path / "d.db"), "VALUE_RAIL_FIXTURES_DIR": str(FIXTURES),
           "VALUE_RAIL_CONFIG_PATH": str(REPO / "config" / "default.toml"),
           "VALUE_RAIL_MIGRATIONS_DIR": str(REPO / "migrations"), "VALUE_RAIL_DB_URL": "", "TYPESAFE_API_KEY": FAKE_KEY}
    res = CliRunner().invoke(app, ["diagnose"], env=env)
    assert res.exit_code == 0 and FAKE_KEY not in res.output
    info = json.loads(res.stdout)["enrichment"]
    assert info == {"enabled": False, "provider_configured": "null", "provider_effective": "null",
                    "typesafe_api_key_present": True, "model": "jev-latest", "judgments_stored": 0}


def test_env_example_has_placeholder_only():
    lines = [l for l in (REPO / ".env.example").read_text().splitlines() if "TYPESAFE_API_KEY" in l]
    assert lines and all(l.strip().startswith("#") and l.strip().endswith("=") for l in lines if "=" in l)


def test_question_definitions_respect_api_limits():
    with pytest.raises(ValueError):
        Question(id="x", kind=JudgmentKind.CHOICE, instructions="?", criteria={f"o{i}": None for i in range(256)})
    with pytest.raises(ValueError):
        Question(id="x", kind=JudgmentKind.SCORE, instructions="?", criteria=["only one"])
    with pytest.raises(ValueError):
        JudgmentRequest(state="s", questions=())
    many = extract_numeric_candidates([("t", " ".join(f"{i} EUR" for i in range(1, 400)))], limit=254)
    assert len(select_face_value(many).options) == 255
