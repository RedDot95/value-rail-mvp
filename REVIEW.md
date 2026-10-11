# CoinGate Clearance Tracker – Review

Production reads only https://coingate.com/gift-cards/clearance and its public browser search inventory. See [source contract](docs/sources.md).

Important code:
- `connectors/coingate_clearance.py`: public configuration discovery, strict resale filter, complete pagination, denomination/price/expiry validation and inventory grouping.
- `valuation/screener.py`: nominal discount; no fee, payout or account assumptions.
- `worker/scan.py`, `worker/sellers.py`: immutable snapshots plus available/gone/returned inventory tracking.
- `alerts/eligibility.py`, `alerts/outbox.py`, `alerts/dispatcher.py`: freshness/expiry/stock revalidation, deduplication and durable delivery retries.
- `tests/test_coingate_clearance.py`: synthetic schema and lifecycle tests.

The historic valuation/replay framework remains available, but is not used for production screening. Former website connectors and research captures are removed. Offline tests never contact providers or Telegram.

Run `pytest`. Start deployment with `docker compose up -d --build` after configuring the local `.env` (see README).
