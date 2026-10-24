# Operational demonstration — 24 October 2026

## What was actually executed

Implementation commit: `fa3bdc5ddefa9e47d13ab77948c67f3c134e2355`. A fresh isolated Python 3.12 environment installed the repository's pinned dependencies and ran its existing offline suite: **326 tests passed in 18.02 seconds**. No new tests or product features were added for this presentation update.

The existing fixture connector, SQLite/Alembic initialization, scan pipeline and FastAPI TestClient rendered ten synthetic evaluations. Dashboard, selected detail and status routes returned HTTP 200; the selected R04 fixture's stored-input replay matched. Health reported live scanning disabled and Telegram unconfigured. No dispatch or external model API ran in this offline demonstration.

## Recorded application responses

- [Dashboard HTML snapshot](demo/dashboard-offline-2026-10-24.html)
- [Detail HTML snapshot](demo/detail-offline-2026-10-24.html)
- [Status HTML snapshot](demo/status-offline-2026-10-24.html)
- [Machine-readable local verification](demo/verification-offline-2026-10-24.json)

These are actual server-rendered responses from the existing application, saved as static files with an added disclosure banner and inactive navigation/controls. Download the HTML and open it locally to inspect the mobile-aware layout. They are not a hosted application, a live-offer demo or a statement of real profit. All fixture amounts and outcomes are synthetic. The optional valuation UI is distinct from the active clearance-only monitoring feed.

## Reproduce the offline application

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
value-rail init-db
value-rail load-fixtures --no-dispatch
value-rail evaluations
value-rail serve
```

Use the default offline configuration and no provider/delivery credentials. Open `http://127.0.0.1:8000`. Keep this unauthenticated demonstration local. The current committed snapshot is one dated execution, not a promise of identical timestamps or database identifiers.

## Live feed and phone delivery

The connected GitHub app successfully read the renamed repository's `clearance-signals/clearance.json`. The first inspected feed was structurally complete and reported `ok`, but its 05:05:54 UTC timestamp was older than the task's two-hour freshness limit. It therefore was not usable evidence of current offers. Scheduled workflow success and freshness are separate checks.

The active task still uses the intended two-runs-per-day, read-only, changes-only contract documented in [ChatGPT Push](chatgpt_push.md). Its activation and prompt were read back; schedule and notification conditions were not changed. No test offer or fake inventory change was published and no test notification was forced.

Phone receipt remains **unverified**. It requires a genuine eligible task result plus confirmation on the intended device; no such receipt evidence was available in this execution. This limitation is independent of the offline UI, source fetch or feed publication.


Manual post-rename live verification: [workflow run 40078614738](https://github.com/SFS-Labs/value-rail-mvp/actions/runs/40078614738) completed successfully on the implementation commit above. The connector read back the newly published feed with `checked_at=2026-10-24T08:35:28.068623+00:00`, `schema_version=1`, `status=ok`, `enumeration_complete=true` and 31 raw offer entries (blob `9177f6cc648b0b5678d58adbc4cf8629347fdd6b`). These are raw feed entries, not a count of task-eligible notifications or profitable opportunities. This verifies the source → workflow → repository publication → connector-read segment after the rename, not phone receipt.

