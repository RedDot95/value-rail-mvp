# Deployment (Delivery 1)

## Ist-Zustand
- **Single-Node, SQLite** (`./data/value_rail.db`, WAL, `synchronous=FULL`). Ein Writer-Prozess zur Zeit vorgesehen
  (Worker **oder** CLI-Scan); Web liest nur. Mehrere gleichzeitige Scanner sind nicht abgesichert (kein Lease/Lock).
- Schema nur über Alembic (`value-rail init-db` = `upgrade head` + Seed; idempotent).
- Web: Uvicorn, SSR. `value-rail serve` bindet standardmäßig `127.0.0.1` und verweigert andere Hosts ohne Basic-Auth.
- Dockerfile vorhanden (python:3.13-slim, Non-Root-User, Volume `/data`, Healthcheck `/healthz`).
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
| Kein Heartbeat/Monitoring | stille Ausfälle unbemerkt | Heartbeat-Ping je Zyklus an externen Dead-Man-Switch; Alarm bei Ausbleiben |
| Kein Backup/Restore | SQLite-Datei ist Single Point of Failure | `sqlite3 .backup` bzw. Litestream nach S3-kompatiblem Speicher; Restore-Probe dokumentieren |
| Kein TLS/Domain | Basic-Auth sonst im Klartext | Reverse-Proxy + Let's Encrypt |
| Kein echter Alert-Kanal | nur Log-Sink | Telegram/Pushover/E-Mail-Sink hinter dem vorhandenen `AlertSink`-Protokoll |
| Kein Scheduler-Lock | doppelte Worker → doppelte Scans | Lease-Tabelle oder Single-Instance-Garantie |
| Keine Live-Connectoren | siehe `docs/sources.md` | Delivery 2 |
