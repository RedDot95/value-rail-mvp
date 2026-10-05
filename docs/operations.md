# Betrieb (Delivery 1 – Offline)

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
value-rail worker --once        # ein Zyklus: Fixture-Scan + Outbox-Dispatch
value-rail worker --cycles 3    # drei Zyklen im Watchlist-Abstand
value-rail worker               # Endlosschleife (Stub – kein Supervisor, kein Lock, kein Heartbeat)
value-rail dispatch             # nur ausstehende Alerts senden (z. B. nach Neustart)
value-rail diagnose             # Konfig, Zähler, Outbox-Zustände, Quellen-Health, letzter Scan
value-rail replay <id>          # Bewertung exakt nachrechnen (Exit 1 bei Abweichung)
```

## Alerts
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

## Heartbeat / Backup / Restore
**Geplant, nicht implementiert.** Vorgesehen: Heartbeat-Ping pro Worker-Zyklus; tägliches `sqlite3 value_rail.db
".backup ..."` bzw. Litestream; dokumentierte Restore-Probe (DB zurückspielen → `value-rail diagnose` →
`value-rail replay` auf Stichproben muss `match: true` liefern).

## Regeländerung
`value-rail rules add --label <neu> --param price_find_min_discount=0.30` legt eine neue, unveränderliche
Regelversion ab jetzt an. Alte Bewertungen bleiben an ihre Version gebunden und sind per `replay` exakt reproduzierbar.
