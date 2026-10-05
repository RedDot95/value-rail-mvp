# Review Brief – Delivery 2 (+ Delivery-3-Basis), Stand 05.10.2026 23:55 CEST

**Ergebnis:** Erster echter Direkt-Connector (Recharge.com DE: Bitsa + paysafecard) implementiert, offline gegen
aufgezeichnete echte Antworten getestet und **einmal live geprüft** (05.10.2026 23:48 CEST: 10 Angebote, alle
„Blockiert“, 0 Preisfunde – korrektes Ergebnis). `pytest`: **162 passed, 1 deselected (live)**, offline auch unter
`unshare -rn`; `pytest -m live`: 1 passed (23:48 CEST). Nichts deployt, nichts gekauft. Lokale Git-Commits, kein Push.

Legende der Spalten: **geplant** (nur Konzept/Konfig) · **implementiert** (Code vorhanden) · **offline getestet**
(automatisierte Tests ohne Netzwerk) · **live geprüft** (gegen echte Quelle ausgeführt, Datum) · **deployed** (auf
Dauer-Host) · **Dauerbetrieb beobachtet** (über Tage überwacht). ✓ = erreicht, – = nicht erreicht.

## Status-Matrix
| Komponente | geplant | implementiert | offline getestet | live geprüft | deployed | Dauerbetrieb beobachtet | Nachweis |
|---|---|---|---|---|---|---|---|
| Domain, Decimal, UTC/Berlin, „unknown“, Mengenfelder, unveränderliche Snapshots | ✓ | ✓ | ✓ | – | – | – | `test_storage.py`, `test_valuation.py` |
| Bewertungs-Engine 1.1.0 (inkl. gedeckelte %-Gebühr) | ✓ | ✓ | ✓ | ✓ (05.10. im Smoke-Scan) | – | – | `test_valuation.py`, `test_exit_rules.py::test_capped_percent_fee` |
| Replay (engine_version separat ausgewiesen) | ✓ | ✓ | ✓ | ✓ (Live-Bewertung per UI-Replay `match: true`) | – | – | `test_replay.py` |
| Fixture-Connector (synthetisch) | ✓ | ✓ | ✓ | n/a | – | – | `test_fixture_scenarios.py` |
| SSRF-sicherer HTTP-Client (Allowlist, IP-Pinning, Redirect-Recheck, Timeouts, Body-Limit) | ✓ | ✓ | ✓ | ✓ (05.10.) | – | – | `test_http_safe.py` (42) |
| Höflichkeit: robots.txt, Crawl-delay, Mindestabstand + Jitter, Backoff | ✓ | ✓ | ✓ | ✓ (05.10., 3 Requests, ≥ 5 s Abstand) | – | – | `test_rate_limit_*`, `test_robots_*` |
| Eigene Fehler (429/403/401/Parser/leer/robots/SSRF) statt „0 Angebote“ | ✓ | ✓ | ✓ | – (live kein Fehler aufgetreten) | – | – | `test_status_mapping_*`, `test_parser_break_*`, `test_http_errors_mark_source_down` |
| **Recharge.com-Connector** (JSON-LD, Parser `recharge-jsonld/1.0.0`, Evidence mit Parser-Version) | ✓ | ✓ | ✓ (Fixtures vom 05.10.) | ✓ (05.10. 23:48 CEST) | – | – | `test_recharge_connector.py`, `docs/live_smoke_2026-10-05.md` |
| Checkout-Quote Recharge | ✓ | – (kein unverbindlicher Quote-Endpunkt) | – | – | – | – | Capability ehrlich `false` |
| Exit-Regeln paysafecard DE (5 %/max 5 €, Tiefe 1, DE-Konto, ID) als RuleVersion | ✓ | ✓ | ✓ | ✓ (in Live-Bewertungen angehängt) | – | – | `test_exit_rules.py`, `config/default.toml` |
| Exit-Regeln Bitsa (SEPA 500 €/Tag, 1,50 € konservativ, Einlösegebühr unknown) | ✓ | ✓ | ✓ | ✓ (blockiert wie erwartet) | – | – | dito |
| Exit Krypto-Gutscheine (Azteco/Bitnovo) | ✓ (recherchiert) | – | – | – | – | – | `docs/sources.md` §2 |
| Bitrefill Personal API | ✓ | – (braucht Nutzer-API-Key) | – | – | – | – | `docs/sources.md` §1 |
| Live-Smoke-Test (`value-rail smoke`, `pytest -m live`) | ✓ | ✓ | ✓ (Bericht offline) | ✓ (05.10.) | – | – | `test_smoke_report_offline_*` |
| Scan-Pipeline atomar (Snapshot+Quotes+Evidenz+Bewertung+Outbox) | ✓ | ✓ | ✓ | ✓ (05.10.) | – | – | Fälle 12–15 |
| Scheduler: DB-Lease (kein Overlap), Job-Status persistent, begrenztes Nachholen | ✓ | ✓ | ✓ | – | – | – | `test_scheduler.py` (9) |
| Heartbeat-Datei, `/healthz` (503 bei stale/failing), `/livez`, `value-rail health` | ✓ | ✓ | ✓ | – | – | – | `test_heartbeat_file_and_healthz_endpoint` |
| Alert-Policy, Outbox, Dispatcher, LogAlertSink | ✓ | ✓ | ✓ | – | – | – | `test_alerts.py` |
| TelegramAlertSink (aus ohne Token+Chat-ID, Token nie in Fehlern) | ✓ | ✓ | ✓ (Fake-Transport, kein Versand) | – (kein Token) | – | – | `test_telegram.py` (9) |
| Web-UI mobil, Basic-Auth | ✓ | ✓ | ✓ | ✓ (zeigt Live-Bewertungen lokal) | – | – | `test_web.py` |
| Dockerfile | ✓ | ✓ | – (kein Docker auf der Box) | – | – | – | |
| TLS/Reverse-Proxy, Backup/Restore, externer Watcher | ✓ | – | – | – | – | – | `docs/deployment.md` |
| 24/7-Hosting | ✓ | – | – | – | – | – | Nutzer-Blocker (Host) |

## Live-Ergebnis 05.10.2026 (Details: `docs/live_smoke_2026-10-05.md`)
- Requests: robots.txt 200, `/en/de/bitsa` 200, `/en/de/paysafecard` 200.
- 10 Angebote: Bitsa 15/25/50/100 €, paysafecard 10/20/30/50/100/150 € – **Preis = Nennwert**, Servicegebühr „ab 0“.
- Alle 10 **Blockiert**: `unknown_required_fee:recharge_service_fee` (+ bei Bitsa `bitsa_voucher_reload_fee`).
  Selbst mit Servicegebühr 0 wäre der Rabatt 0 % (kein Preisfund) und der paysafecard-Rücktausch kostet 5 %
  (50 € → 47,50 €) ⇒ strukturell kein Profit auf dieser Route.

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
1. Geschlossen: `no_signal` bleibt; veraltete vollständige Route bleibt „Abgelaufen“ (D-30). httpx2 verifiziert (D-24).
2. Recharge liefert nur Nennwertpreise ⇒ der Connector beweist die Pipeline, findet aber keine Rabatte. Für echte
   Preisfunde braucht es Quellen mit Rabatt (z. B. Bitrefill-API mit Nutzer-Key) – Entscheidung Nutzer.
3. Ob Recharge.com autorisierte paysafecard-Vertriebsstelle ist, ist unbelegt (Voraussetzung bleibt unknown).
4. Exit-Regeln laufen am 05.11.2026 ab (`review_by`) und müssen dann neu belegt werden.
