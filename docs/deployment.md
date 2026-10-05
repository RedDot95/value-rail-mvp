# Deployment (Stand Delivery 2 + Delivery-3-Basis, 05.10.2026)

## Ist-Zustand
- **Single-Node, SQLite** (`./data/value_rail.db`, WAL, `synchronous=FULL`). Der Worker hält eine **DB-Lease**
  (`scheduler_locks`, TTL 900 s): ein zweiter Worker bleibt im Standby; manuelle CLI-Scans (`value-rail scan`,
  `smoke`) laufen ohne Lease (bewusst, operatorgesteuert).
- Prozesse: `value-rail serve` (Web) und `value-rail worker` (Scheduler, SIGTERM → beendet aktuellen Job, gibt Lease frei).
- Live-Netzwerk: nur ausgehend HTTPS zu `www.recharge.com` (Connector, wenn aktiviert) und `api.telegram.org`
  (wenn Telegram konfiguriert). Keine eingehenden Ports außer der Web-UI.
- Schema nur über Alembic (`value-rail init-db` = `upgrade head` + Seed; idempotent).
- Web: Uvicorn, SSR. `value-rail serve` bindet standardmäßig `127.0.0.1` und verweigert andere Hosts ohne Basic-Auth.
- Dockerfile vorhanden (python:3.13-slim, Non-Root-User, Volume `/data`, Container-Healthcheck `/livez`;
  `/healthz` ist für den externen Watcher gedacht und liefert 503, wenn Jobs veralten).
  **Nicht gebaut/getestet**, da auf der Grok-Bot-Box kein Docker verfügbar ist. Getestet wurde stattdessen eine
  nicht-editierbare Wheel-Installation mit denselben `VALUE_RAIL_*`-Variablen (init-db, load-fixtures, uvicorn).

## Grok-Bot-Box
Die Box kann den Prototyp ausführen (Tests, CLI, UI auf localhost). Sie ist **kein Nachweis für 24/7-Betrieb**:
keine garantierte Uptime, kein Prozess-Supervisor, kein externer Zugriff mit TLS, keine Backups, gemeinsam genutzte
Maschine. Es wurde **nichts deployt** und nichts öffentlich erreichbar gemacht.

## Sicherheit bei externem Zugriff (Pflicht)
1. TLS-terminierender Reverse-Proxy (z. B. Caddy/nginx) vor Uvicorn; Uvicorn nur an localhost/privatem Netz.
2. `VALUE_RAIL_BASIC_USER` / `VALUE_RAIL_BASIC_PASSWORD` setzen (starkes Passwort). Basic-Auth ohne TLS ist unzulässig.
3. Container-Port nur an `127.0.0.1` mappen (`-p 127.0.0.1:8000:8000`).
4. Für mehr als einen Nutzer: richtige Auth (OIDC/Passkey) statt Basic – geplant.

## Blocker für dauerhaftes Hosting
| Blocker | Warum | Vorschlag |
|---------|-------|-----------|
| Kein Host gewählt/bezahlt | Box ist nicht 24/7 | kleiner VPS (EU, wegen DSGVO/Zeitzone) oder Home-Server mit USV |
| Kein Prozess-Supervisor | Worker/Web starten nach Crash/Reboot nicht neu | systemd-Units oder `docker compose` mit `restart: unless-stopped` |
| Kein externer Watcher | Heartbeat-Datei + `/healthz` (503 bei stale/failing) + `value-rail health` (Exit 1) sind **implementiert**, aber niemand beobachtet sie | Uptime-Kuma/Healthchecks.io o. ä. auf `/healthz` (hinter TLS) oder Cron `value-rail health` |
| Kein Backup/Restore | SQLite-Datei ist Single Point of Failure | `sqlite3 .backup` bzw. Litestream nach S3-kompatiblem Speicher; Restore-Probe dokumentieren |
| Kein TLS/Domain | Basic-Auth sonst im Klartext | Reverse-Proxy + Let's Encrypt |
| Telegram nicht konfiguriert | Sink implementiert, aber ohne Token/Chat-ID aus | Nutzer legt Bot via @BotFather an, setzt `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `sink = "log,telegram"` |
| Live-Connector deaktiviert | bewusst opt-in | `recharge` + Job `recharge_scan` aktivieren (30-min-Intervall); liefert derzeit nur „Blockiert“ |
| Bitrefill-API | braucht Nutzer-API-Key (Konto) | Delivery 3, nach Key-Übergabe |

## Beispiel systemd (nicht installiert, Vorlage)
```ini
# /etc/systemd/system/value-rail-worker.service
[Service]
WorkingDirectory=/opt/value-rail-mvp
EnvironmentFile=/opt/value-rail-mvp/.env
ExecStart=/opt/value-rail-mvp/.venv/bin/value-rail worker
Restart=always
RestartSec=10
User=valuerail
[Install]
WantedBy=multi-user.target
```
Analog `value-rail-web.service` mit `ExecStart=... value-rail serve --host 127.0.0.1` hinter Caddy/nginx (TLS).
Watcher: `*/5 * * * * /opt/value-rail-mvp/.venv/bin/value-rail health >/dev/null || <alarm>`.
