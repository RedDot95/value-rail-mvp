# REVIEW.md: Alternative Value Rail Arbitrage MVP (handoff for code review / bug hunt)

Snapshot: 06.10.2026, branch HEAD (local git only, never pushed). Most docs are in German. Start with
`docs/review_brief.md` (status matrix), `docs/sources.md` (per-source access basis) and `docs/decisions.md`.

## What it is
This is a private research tool. It watches gift card and voucher sources (Bitsa, paysafecard, Flexepin, crypto vouchers, etc.),
stores price snapshots with evidence, and values a buy → redeem/exit route using exact Decimal math.
It never buys anything. It never opens a cart, checkout or account. It never bypasses CAPTCHA, Cloudflare or region blocks.

**Route statuses:**
- `verified_route`
- `price_find`
- `expired`
- `blocked`
- `no_signal`

An alert only fires for a verified route or price find. "Unknown" is a first-class value: an unknown required fee, currency or face value blocks the route.
Aggregator sources are `discovery_only` and are never a price basis.

## Architecture (`src/value_rail/`, ~6.4k LOC, Python 3.12+)
| Area | Modules | Notes |
|---|---|---|
| Domain | `domain/{money,identity,entities,enums,timeutil}.py` | Decimal context, `"unknown"` sentinel, product identity (all 6 fields must match), UTC storage / Berlin display |
| Valuation | `valuation/{engine,models,replay}.py` | Pure functions. Status precedence and formulas are in the engine docstring. Replay re-evaluates stored inputs exactly |
| Connectors | `connectors/{base,registry,fixture,recharge,jsonld_shop,aggregators,placeholders}.py` | `Connector` ABC: discovery → offer_fetch → normalize (+ optional quotes). Honest `capabilities()`. Aggregators are hard-wired `discovery_only` |
| Network | `net/{http_safe,robots,errors}.py` | SSRF-safe client: https only, host allowlist, public-IP pinning against DNS rebinding, manual redirect re-validation, size limits, ≥5 s/host + jitter, robots.txt (RFC 9309 matcher), distinct error classes |
| Worker | `worker/{scheduler,scan,sellers,exit_rules}.py` | DB-lease scheduler (one active worker, TTL, dead-local-holder takeover, bounded catch-up). Scan runs fetch first, then one transaction per route. Seller-offer events |
| Alerts | `alerts/{policy,outbox,dispatcher,sinks}.py` | Transactional outbox, dedup/re-alert policy, log sink + optional Telegram (off by default) |
| Storage | `storage/{db,orm,repo,types}.py`, `migrations/` (Alembic 0001–0004) | SQLite. Snapshots are immutable/versioned |
| Ops | `cli.py` (Typer), `web/` (FastAPI + Jinja, Basic Auth), `health.py`, `backup.py`, `smoke.py`, `deploy/` (supervisord, `vrctl`) | |
| Judgments (new) | `judgments/{base,null_provider,typesafe_provider,questions,service,safety}.py`, table `offer_judgments` (Alembic 0004) | Optional TypeSafe System One enrichment/safety layer, **off by default** (null provider, no network). Inferred hints only; see below |

Config: `config/default.toml` (offline/fixtures) and `config/production.toml` (live sources and jobs). Runtime settings come from `.env`
(not in this archive; see `.env.example`).

## Install & test
```bash
uv venv -p 3.13 .venv            # or: python3 -m venv .venv
uv pip install -p .venv/bin/python -e '.[dev]'   # or: .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                 # offline; live tests are excluded via -m 'not live'
.venv/bin/pytest -m live         # opt-in, hits real sites (politely)
.venv/bin/value-rail init-db && .venv/bin/value-rail load-fixtures && .venv/bin/value-rail serve
```
Last run on this snapshot: **254 passed, 2 deselected (live)** (06.10.2026, incl. 35 judgment tests).

## Status
- **Delivery 1:** offline core (DB, valuation, UI, log alerts, synthetic fixtures). Done.
- **Delivery 2:** Recharge.com DE live connector (JSON-LD), SSRF-safe client, sourced exit rules, recorded fixtures, live smoke. Done.
- **Delivery 3:** scheduler/lease, health, backup + restore test, supervisord deployment, generic JSON-LD connector (dundle.com),
  GAMIVO parser (live blocked), new-seller detection. Done.
- **Added 06.10.2026:** aggregator discovery sources: CoinGate (official no-auth MCP, read-only tools), BuySellVouchers list pages,
  CardBear, GiftCardWiki. All daily and `discovery_only`. GCX and GG.deals are blocked. Robots handling switched from `urllib.robotparser` to the RFC 9309 matcher.

- **Added 06.10.2026 (afternoon):** model-judgment enrichment layer (TypeSafe System One / Jev), `docs/decisions.md` D-42.
  Off by default; `value-rail enrich --dry-run` shows the offline path (null provider ⇒ abstain).

## Known issues / blockers
- **Every live route is currently `blocked`.** No connector has a checkout quote (by design, carts are never opened), so a required fee stays `unknown`. There are 0 price finds so far.
- **dundle.com** started returning 403 (incl. robots.txt) around midday 06.10. It is reported as `access_denied_403` / `robots_disallowed` and health is `stale`. It is not bypassed.
- **Blocked sources:** GAMIVO, Eneba, G2A and GG.deals are behind Cloudflare or unreachable; Kinguin, Bitrefill and GCX forbid scraping in their ToS (details in `docs/sources.md`).
- **Box egress is US.** Some sites serve USD or other regions; there is no region spoofing. CardBear and GiftCardWiki are US-only (discount % only).
- **Deployment:** there is no systemd/cron autostart on the dev box. The daily aggregator jobs only take effect after a worker restart.
- **Pending user access:** the BuySellVouchers Buyer API needs an account plus approval; the Bitrefill API needs the user's key.
- **TypeSafe enrichment** needs the user's `TYPESAFE_API_KEY`. On this box `api.typesafe.ai` resolves to `198.18.0.1`
  (egress interception), which the SSRF guard refuses ⇒ provider abstains. The guard was deliberately not relaxed. An authenticated
  success response could not be verified (no key); the parser follows the documented examples and abstains on anything else.

## Please review for bugs in
1. **Valuation Decimal math** (`valuation/engine.py`, `domain/money.py`): discount, profit and edge formulas, fee application (percent with `cap_per_unit`, fixed per order/unit, `included_in_quote`), FX handling, rounding/quantization, quantity selection, stale/expiry precedence, `"unknown"` propagation, replay determinism.
2. **SSRF / robots safety** (`net/http_safe.py`, `net/robots.py`):
   - IP classification (IPv4-mapped, CGNAT, link-local, etc.) and DNS-rebinding pinning;
   - redirect re-validation and login-redirect detection;
   - `post_json` header allowlist;
   - RFC 9309 matching edge cases (group merging, `$`, percent-encoding, tie-break);
   - robots TTL / failure semantics (a 4xx/5xx robots.txt means refuse).
3. **Connector error handling** (`connectors/*`):
   - Check the separation of 429/403/401, ParserBroken, UnexpectedEmpty and genuine zero results. A disturbance must never turn into "no offers" or "seller gone".
   - Check page-error items and `ok_pages` semantics.
   - Check the CoinGate MCP tool allowlist and SSE parsing.
   - Check BSV RSC parsing robustness.
4. **Alert dedup / outbox** (`alerts/*`, `worker/scan.py`): exactly-once enqueue inside the evaluation transaction, re-alert policy, dispatcher retry/backoff/dead-lettering, synthetic alerts never going to Telegram.
5. **Scheduler lock** (`worker/scheduler.py`): lease acquire/renew/expiry races, dead-holder takeover (pid/host check), catch-up bounding, `min_interval_seconds` floor, job-state persistence and the heartbeat/health stale logic.
6. **Judgments / enrichment layer** (`judgments/*`, `worker/scan.py::_enrich_after_scan`, `net/http_safe.py::post_json_authorized`):
   - Can any model output reach the Decimal valuation, the alert outbox or an observed field? (Intended: no. Static import test +
     byte-for-byte scan comparison in `tests/test_judgments.py`.)
   - "Select, don't generate": `questions.resolve_selected_candidate` must only ever return a code-extracted candidate (option keys
     are `candidate_<n>`, never numbers).
   - Safety overlay monotonicity (`judgments/safety.py`): an inferred signal may only add `blocked`, never unlock.
   - Secret handling: `TYPESAFE_API_KEY` (SecretStr) never in logs/diagnose/repr/exception text; bearer token sent only to the exact
     https URL, no redirects followed, token syntax checked (header injection).
   - Off-by-default: `[enrichment].enabled = false` ⇒ nothing imported/constructed in the scan path.
