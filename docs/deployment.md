> Aktueller Stand dieser Sitzung: siehe [Compose-Betrieb](compose_operation.md) und [Ziel/Abdeckung](liquid_value_scope.md). Die nachfolgenden Grok-Box-Angaben stammen aus dem bestehenden Repository; ihre heutige Laufzeit/Persistenz wurde nicht bestätigt.

# Deployment (Stand 06.10.2026 – Dauerbetrieb auf der Grok-Bot-Box)

## Was auf der Box praktisch geprüft wurde (06.10.2026 00:43–00:50 CEST)

| Prüfung | Ergebnis |
|---|---|
| Init-System | PID 1 = `tini` → `pod-daemon`. **Kein systemd** (`/run/systemd/system` fehlt), **kein cron/crond** (weder Binary noch Prozess). |
| Supervisor | Nicht vorinstalliert ⇒ **supervisor 4.3.0 per `uv pip` ins Projekt-venv** (`.venv/bin/supervisord`). |
| Hintergrundprozesse | Ein mit `setsid nohup` gestarteter Prozess lief über mehrere Agent-Shell-Aufrufe weiter (geprüft und danach beendet). supervisord startet ebenfalls per `setsid nohup`. |
| Auto-Restart | `kill -9` auf den Worker ⇒ supervisord startet ihn nach ca. 1 s neu (`exited: worker (terminated by SIGKILL; not expected)` → `spawned`). Der neue Worker übernimmt die DB-Lease **sofort**, weil der lokale Halter-PID tot ist; vorher hätte er bis zu 900 s im Standby gewartet. |
| Persistente Platte | `/workspace` (overlay, 126 GB, 9 % belegt) bleibt über Agent-Sitzungen erhalten. Daten in `data/live/`, Backups in `data/backups/`, Logs in `data/logs/`. |
| Ausgehendes Netz | HTTPS zu dundle.com / recharge.com: 200. Egress-Land laut Cloudflare `US`. |
| Neustart der Box/des Pods | Die Desktop-Prozesse liefen erst seit ca. 1 h 38 min, der Pod wurde also neu gestartet. **Prozesse überleben einen Pod-Neustart nicht.** Es gibt keinen Autostart-Hook (kein systemd, kein cron @reboot). Nach einem Pod-Neustart muss jemand `deploy/vrctl start` ausführen. Ein externer Watcher erkennt das an `value-rail health --json` (Exit 1, `heartbeat.stale = true`). |
| sudo | Passwortlos verfügbar. Nicht genutzt; ein per apt installierter cron würde nach einem Pod-Neustart ebenfalls nicht starten. |
| Docker | nicht vorhanden. |

**Gewählt:** supervisord (Programme `worker` + `web`, `autorestart=true`, `startretries=1000`) gestartet über `deploy/vrctl start` (`setsid nohup`, idempotent).
Logs: `data/logs/worker.log` und `data/logs/web.log`, je 10 MB × 7, sowie `supervisord.log` (5 MB × 5), Rotation durch supervisord.
Socket: `data/run/supervisor.sock` (0700).

## Bedienung
```bash
cd /workspace/value-rail-mvp
deploy/vrctl status            # supervisorctl status + Health-Zusammenfassung
deploy/vrctl start             # startet supervisord, falls nicht läuft (z. B. nach Pod-Neustart)
deploy/vrctl restart worker    # oder: web | all
deploy/vrctl logs worker       # letzte 50 Zeilen
deploy/vrctl health            # = .venv/bin/value-rail health --json (Exit 1 bei stale/failing)
deploy/vrctl stop
```

## Konfiguration
- Die Datei `.env` (chmod 600, git-ignoriert) enthält:
  - `VALUE_RAIL_CONFIG_PATH=config/production.toml`
  - `VALUE_RAIL_DB_PATH=data/live/value_rail.db`
  - Alert-Log, Backup-Verzeichnis und Aufbewahrung (14)
  - `VALUE_RAIL_BASIC_USER=sigma` und `VALUE_RAIL_BASIC_PASSWORD`: 32 Byte `secrets.token_urlsafe`, wird nirgends ausgegeben.
- Passwort nachsehen: `grep BASIC_PASSWORD .env` auf der Box.
- `config/production.toml` enthält die Live-Connectoren und Jobs. `config/default.toml` bleibt die Offline-/Testkonfiguration ohne Live-Connectoren, die Tests nutzen sie.
- Web: `127.0.0.1:8000`, Basic Auth aktiv. `/` ohne Auth ⇒ 401, mit Auth ⇒ 200. `/healthz` und `/livez` sind ohne Auth erreichbar; sie enthalten keine Preise und keine Secrets.

## iPhone-Zugriff (HTTPS + Auth) – NICHT geöffnet, nur geprüft
- Die Box hat keine öffentliche eingehende Adresse (172.30.0.2/24, privat). Möglich ist nur ein **ausgehender Tunnel**.
- Verfügbar: **`cloudflared` 2026.9.3** (`/home/box/.local/bin/cloudflared`). Nicht installiert: tailscale, ngrok, caddy, nginx.
- Optionen, alle **mit Entscheidung oder Konto des Nutzers**:
  1. **Tailscale (empfohlen, nicht öffentlich):** per sudo installieren und mit dem Tailnet des Nutzers verbinden (Login-Link oder Auth-Key vom Nutzer). `tailscale serve --https=443 http://127.0.0.1:8000` liefert ein gültiges HTTPS-Zertifikat für `*.ts.net`. Auf dem iPhone: Tailscale-App, dazu Basic Auth. Problem: tailscaled ohne systemd per supervisord oder userspace-networking betreiben.
  2. **Cloudflare Named Tunnel + Cloudflare Access:** braucht ein Cloudflare-Konto mit Domain (`cloudflared tunnel login` durch den Nutzer). HTTPS kommt von Cloudflare; Access (z. B. E-Mail-OTP) steht zusätzlich vor der Basic Auth. Zu klären, ob `/healthz` freigegeben wird. Tunnel als zusätzliches supervisord-Programm.
  3. **Quick Tunnel (`trycloudflare.com`):** ohne Konto, aber eine öffentliche Zufalls-URL, die nur Basic Auth schützt, ohne Garantie. **Nicht empfohlen.**
- Bis zur Entscheidung bleibt die UI nur lokal erreichbar.

## Backup / Restore
- `value-rail backup` (bzw. Job `backup_daily` alle 24 h im Worker): Online-Backup über die sqlite3-Backup-API nach `data/backups/value_rail_<UTC>.db` (0600). Danach automatisch der **Restore-Test**: Kopie in eine Temp-Datei, `PRAGMA integrity_check` und Vergleich der Zeilenzahlen (offer_snapshots, rule_versions, alerts, route_evaluations, evidence, scan_runs, seller_offers, seller_offer_events). Ergebnis in `data/backups/last_backup.json`, sichtbar in `health.backup`.
- Aufbewahrung: die neuesten 14 Backups (`VALUE_RAIL_BACKUP_KEEP`).
- `value-rail restore-test [datei]` prüft ein bestimmtes Backup.
- Echter Restore: Worker stoppen (`deploy/vrctl stop`), `sqlite3 <backup> ".backup data/live/value_rail.db"` (oder Datei kopieren), dann `deploy/vrctl start`.
- **Grenze:** Die Backups liegen auf derselben Box, sie schützen also vor Bedienfehlern und Korruption, **nicht vor Verlust der Box**. Offen: Offsite-Kopie (z. B. Google Drive oder S3), erst nach Freigabe durch den Nutzer.

## Externer Watcher
`.venv/bin/value-rail health --json` gibt eine Zeile JSON aus, Exit 0 bei ok/starting/degraded, Exit 1 bei stale/failing. Inhalt:
- Worker-Heartbeat (Alter, stale ab 300 s)
- je Quelle letzter Erfolg, Alter, `stale` gegen 3 × kürzestes Job-Intervall
- `stale_sources`
- offene Alerts (`pending`/`dead`)
- je Job die Zahlen des letzten Scans (Kandidaten, Bewertungen, Offers, Status-Verteilung, Seller-Events)
- letztes Backup und Restore-Test

Ein Beobachter, z. B. ein periodischer Grok-Agent, ruft diesen Befehl auf und startet bei Exit 1 mit `deploy/vrctl start` bzw. `restart` neu.

---

# Deployment (Stand Delivery 2 + Delivery-3-Basis, 05.10.2026) – historisch

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
