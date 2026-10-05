# Review Brief – Delivery 1 (Stand 05.10.2026)

**Ergebnis:** Offline-Kern lauffähig. `pytest`: **82 passed, 0 failed** (auch ohne Netzwerk unter `unshare -rn`).
Kein Live-Scan, kein Deployment, keine Käufe. Alle Daten SYNTHETISCH.

Legende: **geplant** = nur Konzept/Doku/Konfig · **implementiert** = Code vorhanden · **offline getestet** = durch
automatisierte Tests mit synthetischen Fixtures abgedeckt.

## Komponenten
| Komponente | Status | Nachweis / Anmerkung |
|------------|--------|----------------------|
| Domain-Entitäten (Source, Product, OfferSnapshot, Asset, Evidence, RuleVersion, Quote, OperatorProfile, RouteEvaluation, ScanRun, Alert, ExecutionResult) | implementiert, offline getestet | `domain/entities.py` (Pydantic) + `storage/orm.py` (Tabellen); `test_storage.py` |
| Decimal-Geld, Float-Ablehnung | implementiert, offline getestet | `test_float_money_rejected`, `test_decimal_and_utc_roundtrip_exact` |
| UTC intern / Europe/Berlin Anzeige | implementiert, offline getestet | `test_decimal_and_utc_roundtrip_exact`, `test_naive_datetime_rejected`; UI zeigt CEST/CET |
| "unknown" statt null | implementiert, offline getestet | u. a. Fall 2/3/6 |
| Getrennte Mengenfelder mit Zeit/Scope | implementiert, offline getestet | Fall 3 |
| Unveränderliche Snapshots + Versionierung | implementiert, offline getestet | ORM-Guard + SQLite-Trigger; `test_snapshots_immutable_orm_guard_and_db_trigger`, `test_correction_creates_new_version`, `test_evaluation_rows_are_immutable` |
| SQLite + Alembic-Migration | implementiert, offline getestet | `test_migration_matches_models` (Autogenerate-Diff leer) |
| Bewertungs-Engine (Rabatt, Profit(q), Edge(q), Schwellen, Status) | implementiert, offline getestet | `test_valuation.py` (32 Tests) |
| Replay / historische Regeländerung | implementiert, offline getestet | `test_replay.py`; CLI `replay`, UI-Link |
| Connector-Interface | implementiert, offline getestet | `connectors/base.py`; `test_connectors.py` |
| Fixture-Connector (offline) | implementiert, offline getestet | 10 synthetische Szenarien, `test_fixture_scenarios.py` |
| Bitsa-/Paysafe-Connector | **geplant** (Platzhalter ohne Fähigkeiten) | `connectors/placeholders.py`; Test prüft, dass nichts behauptet wird |
| Live-Scraper/APIs jeglicher Art | **geplant** (Delivery 2+) | bewusst nicht vorhanden |
| Scan-Pipeline (atomar Snapshot+Bewertung+Outbox) | implementiert, offline getestet | `worker/scan.py`; Fälle 12–15 |
| Scheduler/Worker | implementiert als **Stub**, teilweise offline getestet | `worker/scheduler.py`; `run_cycle` via CLI-Test; Endlosschleife, Lock, Heartbeat **geplant** |
| Alert-Policy (Dedup, Materialität, Restock) | implementiert, offline getestet | Fälle 12, 13 |
| Outbox + Dispatcher (Retries, dead) | implementiert, offline getestet | Fall 14, `test_retries_are_limited_then_dead` |
| LogAlertSink (strukturierte JSON-Logs) | implementiert, offline getestet | `test_case12…` prüft Datei + Log-Records |
| Weitere Sinks (Telegram/Push/E-Mail) | **geplant** | `AlertSink`-Protokoll vorhanden |
| Web-UI mobil (Preisfunde, Verifizierte Routen, Systemstatus, Detail mit Kosten + Evidenz) | implementiert, offline getestet | `test_web.py`; zusätzlich manuell per Headless-Chrome bei 390 px Breite gesichtet |
| Basic-Auth (lokaler Prototyp) | implementiert, offline getestet | `test_basic_auth_enforced_when_configured` |
| TLS / produktive Auth | **geplant** | `docs/deployment.md` |
| CLI (init-db, load-fixtures/scan, dispatch, replay, evaluations, diagnose, worker, serve, rules) | implementiert, offline getestet (außer `serve`/`worker` Endlosschleife) | `test_cli.py`; `serve` manuell gestartet und per curl geprüft |
| Dockerfile / .env.example | implementiert, **nicht getestet** | kein Docker auf der Box; Wheel-Installation mit gleichen Env-Variablen manuell geprüft |
| Heartbeat, Backup/Restore | **geplant** | `docs/operations.md`, `docs/deployment.md` |
| 24/7-Betrieb / Hosting | **geplant**, nicht nachgewiesen | Blocker in `docs/deployment.md` |

## Regressionsfälle des Bauauftrags
| # | Fall | Status | Tests |
|---|------|--------|-------|
| 1 | Aggregator 36 € vs. Direkt 56 €, Nennwert 50 € → Direktpreis, kein Rabatt-Alert | offline getestet | `test_case01_*` (Engine), Szenario `R01_aggregator_vs_direct` (Scan, `alert: false`) |
| 2 | Bitsa 5 € / 1,20 € all-in, Exit unbekannt → 76 %, nur Preisfund, kein EUR-Profit | offline getestet | `test_case02_*`, Szenario `R02_bitsa_price_find` |
| 3 | Paysafe 11 angezeigt, 3 gekauft zu 45 % → 9 € / 4,05 €, Rest/Ursache offen | offline getestet | `test_case03_*`, Szenario `R03_paysafe_partial_qty` |
| 4 | 45 € all-in, Netto-Exit 100 € → 55 € Profit, Edge 122,22…% | offline getestet | `test_case04_*`, Szenario `R04_verified_profit_55` |
| 5 | Unbekannte Pflichtgebühr → Verifizierte Route blockiert | offline getestet | `test_case05_*` (Checkout/Exit/Angebot), Szenario `R05_unknown_required_fee` |
| 6 | Nur "$100" → Währung unknown, kein USD | offline getestet | `test_case06_*` (Parser + Engine), Szenario `R06_dollar_sign_only` |
| 7 | Gleicher Ticker, falscher Contract/Chain → kein Merge | offline getestet | `test_case07_*` (Domain + DB-Constraint) |
| 8 | Veralteter Quote oder falscher Seller/Variante → kein aktueller Treffer | offline getestet | `test_case08_*` (4 Identitätsfelder × Quote/Angebot), Szenarien `R08_*`, `R08b_*` |
| 9 | Exit-Tiefe 2, Angebot 10 → nur 2 bewertet | offline getestet | `test_case09_*`, Szenario `R09_exit_depth_2_of_10` |
| 10 | Höhere Gebühr → Profit steigt nie | offline getestet | `test_case10_*` (3 Gebührenarten × 2 Seiten) |
| 11 | Gebühr bereits im Quote → keine Doppelgebühr | offline getestet | `test_case11_*`, Szenario `R11_fee_included_in_quote` |
| 12 | Identischer Rescan → kein neuer Alert | offline getestet | `test_case12_identical_rescan_no_duplicate_alert`, `test_cli_end_to_end` |
| 13 | Restock / materielle Preisänderung → neues Event | offline getestet | `test_case13_restock_and_material_price_change_create_new_events` |
| 14 | Neustart zwischen Bewertung und Versand → Outbox bleibt, Retry sichtbar | offline getestet | `test_case14_restart_between_evaluation_and_send_keeps_outbox` |
| 15 | Quelle down → Störung statt "keine Deals", Altdaten veraltet | offline getestet | `test_case15_*`, `test_old_data_marked_stale_by_age` |
| 16 | Historische Regeländerung → alte Bewertung exakt reproduzierbar | offline getestet | `test_case16_*`, `test_replay_all_fixture_evaluations` |

## Offene Punkte für das Review
1. **D-07 `no_signal`** als zusätzlicher Status – bestätigen oder anders benennen.
2. **Präzedenz `expired` vor `price_find`** (D-08): Ein vollständiger, aber veralteter Routennachweis wird als
   „Abgelaufen“ gezeigt (mit dem damaligen Profit, deutlich als veraltet markiert), nicht als Preisfund.
3. Materialitätsschwelle 2 % und Restock-Regel sind Startwerte (Konfig).
4. FX: Fremdwährungen werden ohne FX-Quote blockiert; FX-Quellen sind nicht angebunden.
