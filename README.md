# Value Rail — CoinGate Clearance Tracker

A Python monitoring MVP that turns a changing gift-card clearance inventory into filtered, persisted signals. The engineering focus is **source ingestion, deterministic validation, inventory lifecycle tracking and observable delivery workflows**.

**Current milestone:** scheduled GitHub Actions feed with an optional self-hosted worker and web UI. This is an evolving personal project. A nominal discount is a price observation; it does not establish an executable trade, net return or commercial result.

## What is implemented

| Component | Implementation | Boundary |
|---|---|---|
| Source adapter | CoinGate clearance only; clearance filter, pagination, price/denomination/expiry checks | Source schema and availability can change |
| Signal logic | Nominal-discount filtering, new/changed/returned inventory state | Fees, redemption eligibility and payout are not inferred |
| Published feed | Scheduled workflow writes `clearance.json` to `clearance-signals` | Workflow scheduling is best-effort; inspect timestamps/status |
| Delivery | ChatGPT feed consumption; optional outbox/Telegram/log sinks | Phone push depends on a separate task and notification settings |
| Local operations | SQLite/Alembic, CLI, worker health, backups, replay and FastAPI UI | Optional deployment needs configuration and its own verification |
| Regression suite | Offline synthetic source/lifecycle, valuation, storage, alert and UI tests | Synthetic fixtures do not establish live-market accuracy |

Only [CoinGate Clearance](https://coingate.com/gift-cards/clearance) is enabled for real market ingestion. The older valuation/replay framework remains in the code; the active clearance screener does not use it to claim net profitability.

## Architecture

`CoinGate clearance → connector → validation/filtering → inventory state → signal feed`

The optional worker persists snapshots/evaluations in SQLite and uses a delivery outbox. The web application reads operational state. Synthetic fixtures exercise the broader framework independently of the live source.

- [Review guide and important code](REVIEW.md)
- [Source contract](docs/sources.md)
- [Feed and ChatGPT integration](docs/chatgpt_push.md)
- [Architecture decisions](docs/decisions.md)
- [Worker operations](docs/compose_operation.md)
- [Quote evidence and valuation boundaries](docs/quote_intake.md)

## Offline quickstart

Python 3.12+; use a fresh environment without live-provider or delivery credentials:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
value-rail init-db
value-rail load-fixtures --no-dispatch
value-rail evaluations
value-rail serve
```

Open `http://127.0.0.1:8000`. The default configuration uses synthetic offline fixtures. `pytest` excludes tests marked `live` by default. Do not confuse fixture outputs with real offers.

## Verified evidence

- Reviewed implementation: `1d27c69e9f0ab2359eb3ba636867638b37a79b0a`.
- [Offline CI run 38668234312](https://github.com/SFS-Labs/value-rail-mvp/actions/runs/38668234312): **success** on that commit for Python 3.12 and 3.13; package installation, pytest and Compose configuration checks passed. This existing CI evidence was reused during the 24 October portfolio review; no fresh local full-suite result is claimed.
- [Scheduled feed run 40032371746](https://github.com/SFS-Labs/value-rail-mvp/actions/runs/40032371746): **success** on the same implementation commit. A successful job is not proof of current stock, user-phone delivery or profitable execution.
- [Historical 10 October validation](docs/clearance_validation_2026-10-10.md) records its dated source observations and 323 offline tests. Those inventory counts are historical snapshots.

## Optional worker deployment

Configure local credentials following [the operating guide](docs/compose_operation.md), then:

```bash
docker compose up -d --build
```

The UI is at `http://localhost:8000`. Without Telegram configuration, delivery uses logging. A worker host must remain running. The scheduled GitHub feed itself does not require a user-owned permanent server. No credentials belong in git.

## Contribution attribution

Mathias Steinbach owns the use case, requirements and ongoing development direction. Implementation, review and documentation use AI-assisted development. Git history and PR discussions are the available provenance; an account author field does not prove manual authorship of every line. This portfolio review changed presentation only and did not independently establish a per-component split between earlier AI tools and manual work.

## Next milestones

1. Keep source-schema/freshness and outage evidence current.
2. Verify the full notification path on the intended device and record its limits.
3. Strengthen reproducible deployment/restore evidence for the optional worker.
4. Extend sources or valuation only when scope, permissions and actual quote evidence justify it.

No automated purchases, confirmed net-return claims or completed enterprise deployment are presented.
