# Value Rail MVP – Delivery 1 (Offline-Kern)

Umsetzung von Delivery 1 aus dem freigegebenen Bauauftrag (04.10.2026): ausführbarer **Offline-Kern** mit
Datenbank, synthetischen Fixtures, Bewertungslogik, mobiler FastAPI-Oberfläche und Log-Alerts.

> **Wichtig:** Alle mitgelieferten Daten sind **SYNTHETISCH** (fiktive Händler/Preise). Es gibt **keinen Live-Scan**,
> **keine Käufe**, **keine erfundenen Marktplatz-Endpunkte**. Der Status jeder Komponente steht in
> [`docs/review_brief.md`](docs/review_brief.md).

## Voraussetzungen
- Python ≥ 3.12 (entwickelt/getestet mit 3.13.5)
- `uv` (empfohlen) oder `pip`

## Installation
```bash
cd /workspace/value-rail-mvp
uv venv -p 3.13 .venv                      # oder: python3 -m venv .venv
uv pip install -p .venv/bin/python -e '.[dev]'   # oder: .venv/bin/pip install -e '.[dev]'
cp .env.example .env                       # optional
```

## Tests (offline)
```bash
.venv/bin/pytest            # 82 Tests, laufen ohne Netzwerk (auch unter `unshare -rn` geprüft)
```

## Datenbank + Fixtures laden
```bash
.venv/bin/value-rail init-db          # Alembic-Migrationen + Seed (Regelversion, SYNTHETIC-Operator)
.venv/bin/value-rail load-fixtures    # ein Offline-Scan über tests/fixtures/scenarios + Log-Alerts
.venv/bin/value-rail load-fixtures    # erneut: 0 neue Alerts (Dedup)
.venv/bin/value-rail load-fixtures --down synthetic-bitsa-reseller   # simulierte Quellenstörung
.venv/bin/value-rail evaluations      # letzte Bewertung je Route
.venv/bin/value-rail replay 4         # exakter Replay einer gespeicherten Bewertung (Exit-Code 1 bei Abweichung)
.venv/bin/value-rail diagnose         # Konfiguration, DB-Zustand, Connector-Capabilities
.venv/bin/value-rail rules list       # Regelversionen; neue: rules add --label X --param price_find_min_discount=0.30
.venv/bin/value-rail worker --once    # Scheduler-STUB: ein Zyklus (Fixture-Scan + Outbox-Dispatch)
```
Standard-DB: `./data/value_rail.db` (persistenter Pfad, via `VALUE_RAIL_DB_PATH` änderbar).
Alerts: strukturierte JSON-Zeilen auf stderr **und** in `./data/alerts.log`.

## Web-UI starten
```bash
.venv/bin/value-rail serve                          # http://127.0.0.1:8000  (nur localhost)
# alternativ direkt:
.venv/bin/uvicorn value_rail.web.app:create_app --factory --host 127.0.0.1 --port 8000
```
Seiten: `/` (Systemstatus, Verifizierte Routen, Preisfunde, eingeklappt: Abgelaufen/Blockiert/Kein Signal),
`/evaluations/{id}` (Kostenaufstellung, Evidenz, Replay), `/status`, `/healthz`, `/api/evaluations`.
Basic-Auth wird aktiv, sobald `VALUE_RAIL_BASIC_USER` und `VALUE_RAIL_BASIC_PASSWORD` gesetzt sind.
`value-rail serve` verweigert nicht-lokale Hosts ohne Auth. **Externer Zugriff nur mit TLS + Auth** (siehe `docs/deployment.md`).

## Docker (nicht im Box-Umfeld gebaut – kein Docker verfügbar)
```bash
docker build -t value-rail-mvp .
docker run --rm -p 127.0.0.1:8000:8000 -v value_rail_data:/data value-rail-mvp
docker exec <container> value-rail load-fixtures
```

## Layout
```
config/default.toml          Regeln (versioniert), Alert-Policy, Scan-Intervalle, Connector-Registry
src/value_rail/domain/       Entitäten (Pydantic), Enums, Identität, Decimal-/Zeit-Helfer
src/value_rail/connectors/   Connector-Interface, Offline-Fixture-Connector, Bitsa/Paysafe-Platzhalter
src/value_rail/normalization Preistext-Parsing (Währung "unknown" bei "$"), Asset-Normalisierung
src/value_rail/evidence/     Evidenz-Hashing/-Entwürfe
src/value_rail/valuation/    Bewertungs-Engine (exakte Formeln), Replay
src/value_rail/storage/      SQLAlchemy-ORM, Decimal-/UTC-Typen, Repository, Engine/Migration
src/value_rail/worker/       Scan-Pipeline (atomar: Snapshot + Bewertung + Outbox), Scheduler-Stub
src/value_rail/alerts/       Dedup-/Materialitäts-Policy, Outbox, Sinks (LogAlertSink), Dispatcher
src/value_rail/web/          FastAPI + Jinja2 SSR, mobile-first
src/value_rail/cli.py        CLI (Typer)
migrations/                  Alembic (inkl. SQLite-Trigger für unveränderliche Tabellen)
tests/fixtures/              SYNTHETISCHE Szenarien + Operator-Profil
docs/                        sources, decisions, deployment, operations, review_brief
```
Alembic-CLI direkt: `.venv/bin/alembic -c pyproject.toml upgrade head` (Konfiguration in `[tool.alembic]`).
