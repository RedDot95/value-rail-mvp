# Value Rail – Screener für liquide Gutscheine

Das Produkt beobachtet Zahlungs-/Kryptogutscheine und Gutscheine großer Händler und meldet konkrete Angebote unter Nennwert als **Arbitrage-Kandidaten**. Gaming, Streaming und Content-Abos sind ausgeschlossen. Auszahlung, vorhandene Konten und Gebühren werden im Produktions-Screener nicht geprüft.

**Produktionsmodus:** `config/production.toml`, `evaluation_mode = "screener"`. Standardmäßig gibt es ab 1 % beobachtetem Rabatt ein Signal; `price_find_min_discount` ist einstellbar. Ein Signal enthält Angebotspreis, Nennwert, Währung, Händler, Region, angezeigten Bestand, Zeitpunkt und Angebotslink. Kein fiktiver Nettogewinn wird berechnet.

Direktangebote laufen alle 5 Minuten, Marktplatz-/Vergleichsquellen alle 30 Minuten. Identische Angebote erzeugen keinen neuen Push; wesentliche Preisänderungen, Wiederverfügbarkeit und erneutes Unterschreiten der Signalschwelle erzeugen neue Ereignisse. Vor Versand werden Alter, Verfügbarkeit, Preis, Quellenstatus und Suchumfang erneut geprüft. Fehlgeschlagene Zustellungen werden wiederholt; erfolgreiche Kanäle haben dauerhafte Quittungen.

**Start:** [Docker-Compose-Anleitung](docs/compose_operation.md). Telegram wird aktiviert, sobald Bot-Token und Chat-ID in der lokalen `.env` gesetzt sind. Ohne diese Daten gibt es Log-Ausgaben, aber keine Handy-Pushes. Der Stack muss für laufendes Tracking auf einem dauerhaft verfügbaren Host laufen.

[Suchumfang und Grenzen](docs/liquid_value_scope.md): 75 Katalogkandidaten, davon 15 Familien mit expliziten Abrufzielen plus Kategorie-Sweeps. Das ist eine erweiterbare Suchliste; nicht jeder Katalogeintrag hat eine funktionierende Quelle. Prozentwerbung ohne konkreten Preis/Nennwert ist kein Signal. `value-rail coverage --json` und `/status` zeigen die tatsächliche Abdeckung.

Die klassische Route-/Quote-Bewertung bleibt als optionaler Modus für historische Bewertungen und Replay erhalten. Sie blockiert den Produktions-Screener nicht. Die Offline-Fixtures sind synthetisch; der Offline-Standard verwendet weiterhin `config/default.toml`.

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
.venv/bin/pytest            # Offline-Regressionen; Live-Tests sind standardmäßig ausgeschlossen
.venv/bin/pytest -m live    # LIVE-Tests (Netzwerk!) - nur bewusst ausführen
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
.venv/bin/value-rail worker --once    # ein Scheduler-Tick (Lease, fällige Jobs, Dispatch, Heartbeat)
.venv/bin/value-rail health           # /healthz-JSON; Exit 1 bei stale/failing (für externe Watcher)
.venv/bin/value-rail enrich --dry-run # optionaler Modell-Enrichment-Pfad offline (Null-Provider ⇒ abstain), D-42
```

## Live-Smoke-Test (echtes Netzwerk, opt-in)
```bash
.venv/bin/value-rail smoke recharge   # 3 Requests (robots.txt + 2 Produktseiten, >= 5 s Abstand + Jitter)
                                      # schreibt docs/live_smoke_<Datum Berlin>.md und speichert die Bewertungen in der DB
```
Ergebnis 05.10.2026 23:48 CEST: 10 Angebote, alle **Blockiert** (Servicegebühr unbekannt; Preis = Nennwert), 0 Preisfunde.
Dauerhaft aktivieren: in `config/default.toml` beim Connector `recharge` **und** Job `recharge_scan` `enabled = true`.

## Telegram (optional, standardmäßig aus)
`TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` setzen **und** `[alerts] sink = "log,telegram"`. Ohne beide Werte wird
nichts gesendet (Warnung im Log). Synthetische Alerts gehen nie an Telegram (`telegram_send_synthetic = false`).
Standard-DB: `./data/value_rail.db` (persistenter Pfad, via `VALUE_RAIL_DB_PATH` änderbar).
Alerts: strukturierte JSON-Zeilen auf stderr **und** in `./data/alerts.log`.

## Web-UI starten
```bash
.venv/bin/value-rail serve                          # http://127.0.0.1:8000  (nur localhost)
# alternativ direkt:
.venv/bin/uvicorn value_rail.web.app:create_app --factory --host 127.0.0.1 --port 8000
```
Seiten: `/` (Systemstatus, Verifizierte Routen, Preisfunde, eingeklappt: Abgelaufen/Blockiert/Kein Signal),
`/evaluations/{id}` (Kostenaufstellung, Evidenz, Replay), `/status`, `/healthz` (Job-Frische, 503 bei stale),
`/livez`, `/api/evaluations`.
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
src/value_rail/connectors/   Connector-Interface, Fixture-Connector, Recharge.com-Connector (JSON-LD), Platzhalter
src/value_rail/net/          SSRF-sicherer HTTP-Client (Allowlist, IP-Pinning, Redirect-Prüfung, robots, Rate-Limit), Fehlerklassen
src/value_rail/normalization Preistext-Parsing (Währung "unknown" bei "$"), Asset-Normalisierung
src/value_rail/evidence/     Evidenz-Hashing/-Entwürfe
src/value_rail/valuation/    Bewertungs-Engine (exakte Formeln), Replay
src/value_rail/storage/      SQLAlchemy-ORM, Decimal-/UTC-Typen, Repository, Engine/Migration
src/value_rail/worker/       Scan-Pipeline (atomar), Exit-Regel-Quotes, Scheduler (Lease, Job-Status, Catch-up, Heartbeat)
src/value_rail/alerts/       Dedup-/Materialitäts-Policy, Outbox, Sinks (Log, Telegram, Composite), Dispatcher
src/value_rail/judgments/    optionale Modell-Urteile (TypeSafe), nur inferierte Hinweise, standardmäßig AUS (D-42)
src/value_rail/health.py     Health-Modell für /healthz und `value-rail health`
src/value_rail/smoke.py      Live-Smoke-Test + Markdown-Bericht
src/value_rail/web/          FastAPI + Jinja2 SSR, mobile-first
src/value_rail/cli.py        CLI (Typer)
migrations/                  Alembic (inkl. SQLite-Trigger für unveränderliche Tabellen)
tests/fixtures/              SYNTHETISCHE Szenarien + Operator-Profil; recorded/ = echte, bereinigte Antworten (05.10.2026)
research/2026-10-05/         Rohquellen (robots.txt, Text-Auszüge der AGB/Gebührenseiten)
docs/                        sources, decisions, deployment, operations, review_brief
```
Alembic-CLI direkt: `.venv/bin/alembic -c pyproject.toml upgrade head` (Konfiguration in `[tool.alembic]`).

Währungsübergreifende Angebote werden mit öffentlichen täglichen ECB-Referenzkursen verglichen. Originalwährungen bleiben sichtbar; Kurse einschließlich Datum und Antwort-Hash werden mit der Bewertung gespeichert. Ohne passenden gültigen Kurs entsteht kein Signal. Referenzkurse sind keine verbindlichen Umtauschkurse.
