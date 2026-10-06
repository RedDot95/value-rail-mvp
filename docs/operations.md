# Betrieb (Stand 06.10.2026 – 24/7 auf der Box)

## Jobs in Produktion (`config/production.toml`)
| Job | Connector | Intervall | Seiten |
|---|---|---|---|
| `recharge_watch` | recharge | 300 s (Watchlist) | /en/de/bitsa, /en/de/paysafecard, /en/de/crypto-voucher |
| `dundle_watch` | dundle | 300 s (Watchlist) | /de/paysafecard/, /de/bitsa/ |
| `dundle_sellers` | dundle | 1800 s (neue Seller/Stückelungen) | Watchlist + /de/azteco/ (`absent_ok`) |
| `gamivo_watch` / `gamivo_sellers` | gamivo | 300 / 1800 s | **aus**, Quelle blocked (Cloudflare Challenge) |
| `backup_daily` | – | 86400 s | Online-Backup + Restore-Test |

- Aggregatoren-Job (täglich) gibt es nicht, weil kein Aggregator nutzbar ist (siehe `docs/sources.md` §0).
- `min_interval_seconds` ist eine Untergrenze je Job (Default 60 s). Kein Job läuft häufiger als konfiguriert erlaubt.
- Jeder Connector hält **eine** Client-Instanz für Watch- und Sweep-Job: ≥ 5 s je Host (GAMIVO 6 s) plus 0–2 s Jitter, robots.txt (24 h gecacht, danach neu gelesen) und Crawl-delay werden beachtet.

## Befehle (Produktion)
```bash
deploy/vrctl status | start | restart [worker|web|all] | logs [worker|web] | health | stop
.venv/bin/value-rail health --json      # externer Watcher (Exit 1 bei stale/failing)
.venv/bin/value-rail backup             # sofortiges Backup + Restore-Test
.venv/bin/value-rail restore-test       # neuestes Backup prüfen
.venv/bin/value-rail smoke dundle       # LIVE-Smoke einer Quelle -> docs/live_smoke_<Datum>_<key>.md
.venv/bin/python scripts/record_fixtures.py dundle   # neue datierte Offline-Fixtures aufnehmen
```

## Modell-Enrichment (TypeSafe, optional, D-42) – standardmäßig AUS
Inferierte Hinweise (Einschränkungsrisiko Region/KYC, Block-Seiten-Verdacht, Instrument-Familie, Nennwert-Auswahl) in
`offer_judgments`. Ändert **nie** Bewertung, Rabatt/Profit/Edge oder Alerts; löst nie eine Aktion aus.

Einschalten (Produktion):
1. `TYPESAFE_API_KEY=<key>` in die Umgebung des Workers bzw. in `.env` (nur serverseitig; nie committen, nie ausgeben).
   Der Schlüssel kann nur vom Nutzer kommen (https://console.typesafe.ai).
2. In `config/production.toml` (oder `config/default.toml`):
   ```toml
   [enrichment]
   enabled = true
   provider = "typesafe"      # "null" = kein Netzwerk, nur abstain
   # optional: model = "jev-1.13.0" (Version pinnen), max_requests_per_scan = 50, max_questions_per_offer = 4
   ```
3. `deploy/vrctl restart worker` (Worker liest die Konfiguration beim Start).
4. Prüfen: `value-rail diagnose` ⇒ `"enrichment": {"enabled": true, "provider_effective": "typesafe", "typesafe_api_key_present": true}`
   (der Schlüssel selbst wird nie ausgegeben). Offline-Pfad jederzeit: `value-rail enrich --dry-run`.
   Nachträglich für die letzten Bewertungen: `value-rail enrich` (nur bei `enabled = true`; schreibt nur `offer_judgments`).

Ohne Schlüssel oder mit `provider = "typesafe"` aber leerem Key ⇒ Warnung im Log und Null-Provider (kein Netzwerk).
**Box-Blocker:** Auf dieser Box löst `api.typesafe.ai` auf `198.18.0.1` (Egress-Abfangung) auf; der SSRF-Guard verweigert
nicht-öffentliche Ziele ⇒ jede Anfrage endet als `blocked_url` ⇒ abstain (Scan läuft unverändert weiter). Vor Livebetrieb
auf der Box: entweder DNS liefert öffentliche Adressen, oder der Nutzer entscheidet ausdrücklich über eine eng begrenzte
Ausnahme (nicht implementiert). Auf einem normalen Host (VPS) entfällt der Blocker.
Anzeige: Detailseite einer Bewertung, Karte „Inferred (Modell) – keine beobachteten Fakten“ (gestrichelt), nur bei `enabled`.
`/healthz` enthält bei `enabled` zusätzlich `inferred_last_24h` (rein informativ, ändert Status/HTTP-Code nicht).

---

# Betrieb (Stand Delivery 2 + Delivery-3-Basis) – historisch

## Scan-Intervalle (aus dem Bauauftrag, `config/default.toml [scan_intervals]`)
| Klasse | Intervall | Delivery-1-Stand |
|--------|-----------|------------------|
| Watchlist | 5 min (`watchlist_seconds = 300`) | Scheduler-Stub nutzt dieses Intervall für den **Offline-Fixture-Scan** |
| Neue Seller | 30 min (`new_sellers_seconds = 1800`) | nur Konfiguration, keine Seller-Discovery implementiert |
| Aggregatoren | täglich (`aggregator_seconds = 86400`) | nur Konfiguration; Aggregatoren sind ohnehin nur Discovery |
| Veraltet nach | 15 min (`stale_after_seconds = 900`) | UI markiert ältere Bewertungen/Scans als veraltet |

Quote-Frische (Bewertungsregel, versioniert): `max_quote_age_seconds = 900`, `max_offer_age_seconds = 3600`.

## Befehle
```bash
value-rail worker --once        # ein Tick: Lease holen, fällige Jobs ([[jobs]]), Dispatch, Heartbeat schreiben
value-rail worker --cycles 3    # drei Ticks im Abstand [scheduler].tick_seconds (15 s)
value-rail worker               # Dauerschleife; SIGTERM = sauber beenden (Lease wird freigegeben)
value-rail health               # Health-JSON; Exit 1 bei stale/failing
value-rail smoke recharge       # LIVE-Smoke-Test (Netzwerk) + docs/live_smoke_<Datum>.md
value-rail dispatch             # nur ausstehende Alerts senden (z. B. nach Neustart)
value-rail diagnose             # Konfig, Zähler, Outbox-Zustände, Quellen-Health, letzter Scan
value-rail replay <id>          # Bewertung exakt nachrechnen (Exit 1 bei Abweichung)
```

## Alerts
- Telegram: `TelegramAlertSink` nur mit `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` + `sink = "log,telegram"`; Fehlertexte
  ohne Token; synthetische Alerts werden nicht an Telegram gesendet.
- Sink: `LogAlertSink` – eine JSON-Zeile pro Alert (`"type": "value_rail.alert"`, `event_id`, Status, Rabatt,
  Profit, fehlende Nachweise, `synthetic`) auf stderr und in `data/alerts.log` (`VALUE_RAIL_ALERT_LOG_FILE`).
- Outbox-Zustände: `pending` → `sent` | `dead` (nach 5 Fehlversuchen, Backoff 60 s × Versuch).
- **Duplikate möglich** (at-least-once): Absturz nach Zustellung, vor Commit → erneute Zustellung mit gleicher `event_id`.
- Nicht alarmiert: `blocked`, `expired`, `no_signal`.

## Störungen
- Quelle nicht erreichbar → Quelle `down` (mit Fehlertext/Zeit), Scan `degraded`, Route nicht neu bewertet.
  UI-Systemstatus rot: „Störung … keine Aussage über Angebote dieser Quelle (Störung ≠ keine Deals)“; betroffene
  Karten tragen „Quelle gestört“.
- Simulation: `value-rail load-fixtures --down synthetic-bitsa-reseller`.

## Scheduler / Heartbeat / Health (implementiert, offline getestet)
- Jobs in `config/default.toml [[jobs]]`: `fixture_scan` (300 s, an), `recharge_scan` (1800 s, **aus**).
- Job-Status persistent in `job_states` (letzter Start/Erfolg/Fehler, Fehlerserie, Läufe, übersprungene Slots).
- Begrenztes Nachholen: nach Ausfall läuft ein fälliger Job höchstens `max_catchup_runs` (1) mal; Rest wird gezählt.
- Heartbeat: `data/heartbeat.json` (atomar ersetzt) nach jedem Tick – `written_at`, Lease-Halter, Jobs.
- `/healthz` (ohne Auth, keine Preise/Secrets): `ok` | `starting` | `degraded` | `stale` (503) | `failing` (503) | `no_jobs`;
  pro Job `last_success_at` + Berlin-Zeit + Alter. `/livez` = Prozess lebt.

## Backup / Restore
**Geplant, nicht implementiert.** Vorgesehen: tägliches `sqlite3 value_rail.db ".backup ..."` bzw. Litestream;
Restore-Probe (DB zurückspielen → `value-rail diagnose` → `value-rail replay` auf Stichproben muss `match: true` liefern).

## Live-Connector Recharge.com
- Höflichkeit: robots.txt wird vor dem ersten Request gelesen (nicht lesbar ⇒ kein Crawl), Abstand ≥ max(5 s,
  Crawl-delay 1 s) + 0–2 s Jitter, Backoff nur bei 5xx/Netzfehlern; 429/403 werden **nicht** wiederholt.
- Fehlerbilder im Systemstatus/`sources_failed`: `[rate_limited_429]`, `[access_denied_403]`, `[auth_lost]`,
  `[parser_broken]` (JSON-LD fehlt/geändert → Parser anpassen, neue Fixture aufnehmen), `[unexpected_empty]`,
  `[robots_disallowed]`, `[blocked_url]`, `[network_error]`, `[upstream_error]`.
- Exit-Regeln (`rules.exit_rules`) haben `review_by` = 05.11.2026: danach werden abgeleitete Exit-Quotes
  `Abgelaufen`, bis die Quellen neu geprüft und ein neues Regel-Label eingespielt wurde.

## Regeländerung
`value-rail rules add --label <neu> --param price_find_min_discount=0.30` legt eine neue, unveränderliche
Regelversion ab jetzt an. Alte Bewertungen bleiben an ihre Version gebunden und sind per `replay` exakt reproduzierbar.
