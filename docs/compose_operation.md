# Betrieb mit Docker Compose

Der Compose-Stack enthält einmalige DB-Migration/Seed, Worker und Weboberfläche. SQLite, Heartbeat, Alert-Log und Backups teilen ein benanntes Volume. Worker/Web starten nach erfolgreichem Init und erhalten `restart: unless-stopped`. Das setzt einen dauerhaft verfügbaren Docker-Host und einen beim Hoststart gestarteten Docker-Dienst voraus; eine temporäre Agent-Umgebung beweist keinen 24/7-Betrieb.

## Start

Im Repository eine lokale, git-ignorierte `.env` anlegen. Benutzer und ein starkes zufälliges Passwort setzen:

```dotenv
VALUE_RAIL_BASIC_USER=value-rail
VALUE_RAIL_BASIC_PASSWORD=<zufälliges-starkes-Passwort>
VALUE_RAIL_TELEGRAM_BOT_TOKEN=<Bot-Token>
VALUE_RAIL_TELEGRAM_CHAT_ID=<Chat-ID>
```

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail 50 worker
docker compose exec worker value-rail coverage --json
docker compose exec worker value-rail health --json
```

Die Weboberfläche bindet an `127.0.0.1:8000`; vor Zugriff von außen einen privaten Zugang oder TLS-Reverse-Proxy einrichten. Der Server verlangt für `0.0.0.0` Basic Auth und startet ohne vollständige Zugangsdaten nicht. Produktions-Sink ist `log,telegram`. Für Handy-Pushes einen Bot über Telegram @BotFather erstellen, den Bot im Zielchat starten und dessen Token sowie die eigene Chat-ID oben setzen. Token nicht ins Repository oder in öffentliche Logs schreiben. Ohne beide Variablen läuft der Screener mit Log-Ausgaben; Telegram ist dann deaktiviert. `/healthz` weist `telegram_configured` aus. Die Standard-Signalschwelle ist 1 % nominaler Rabatt, einstellbar in `config/production.toml`.

Die Jobs aus `config/production.toml` beobachten öffentliche Direktangebote alle 5 Minuten, weitere Quellen alle 30 Minuten und erstellen tägliche lokale Backups. Gebühren und Auszahlungswege werden nicht geprüft. `unhealthy` meldet gestörte/veraltete Jobs, bewirkt in Compose aber **keinen automatischen Neustart**; Neustarts gelten für beendete Prozesse. Ein externer Watcher muss `/healthz` überwachen und Störungen melden. Während eines langen ersten Scans kann der Heartbeat noch fehlen. Das ist kein Beweis dafür, dass alle Quellen erfolgreich laufen.

## Updates und Daten

Vor einem Update ein Backup erstellen und eine Kopie außerhalb des Hosts sichern:

```bash
docker compose exec worker value-rail backup
docker compose stop worker web
docker compose up -d --build
```

`init-db` wendet auch Migration 0005 an: dauerhafte Zustellquittungen je Alert-Kanal. DB, originale Bewertungen und Regeln werden nicht überschrieben. Die Katalog- und Produktionsregeländerung wird unter einem neuen Regel-Label angelegt. Ein bewusstes Herunterstufen der Migration entfernt die neuen Quittungen; nur mit gestopptem Worker und vorherigem Backup durchführen.

Lokale Backups schützen nicht vor Verlust des Docker-Hosts. `docker compose down` behält das Volume; **`down -v` löscht es**. Eine bestehende Grok-Box oder ihr Supervisor wurde in dieser Sitzung nicht verändert.

## Versand und Sperren

Der aktive Worker erneuert seine DB-Sperre im Hintergrund und prüft Besitz vor/nach Netzabfragen sowie in Schreibtransaktionen. Verlust stoppt neue Ergebnis-Commits. Bereits laufende HTTP-Requests lassen sich dadurch nicht zurücknehmen. CLI-Smoke/Scans bleiben ausdrücklich manuelle Läufe ohne Scheduler-Sperre.

Ein gesonderter Dispatch-Lock verhindert parallele Zustellung derselben Pending-Zeilen. Netzwerkversand hält keine DB-Schreibtransaktion offen. Erfolgreiche Kanäle werden dauerhaft gespeichert und bei Retry ausgelassen. Ein Absturz nach externer Zustellung, aber vor der Quittung, kann weiterhin eine Nachricht doppelt zustellen; die Garantie bleibt **at least once**. Empfänger können die stabile `event_id` zur Deduplizierung verwenden.

Unterdrückte veraltete Meldungen blockieren spätere neu belegte Routen nicht. Historische Bewertungen/Regeln bleiben unverändert. Replay nutzt die aktuelle Engine 1.4.0 und kann bei korrigierten Fällen vom historischen Ergebnis abweichen.

## Prüfung in dieser Sitzung

Die vollständige Offline-Suite, Compose-Konfiguration und ein echtes Docker-Build wurden lokal geprüft. Der Container-Test verwendet ausschließlich synthetische Offline-Fixtures: Migration, Worker-Tick, persistente Daten, JSON-Katalog, Web-Auth, `/livez` und `/healthz`. Live-Quellen wurden separat und zeitlich begrenzt geprüft; siehe [Ziel und Abdeckung](liquid_value_scope.md). Der Stack wurde nicht als dauerhafter Produktionsdienst auf einem Nutzer-Host eingerichtet.

Bei einem HTTPS-Proxy kann ein Build eine zusätzliche CA benötigen: `docker build --secret id=proxy_ca,src=/pfad/zum/ca-bundle -t value-rail-mvp:local .`. Die CA wird nur für pip gemountet und nicht ins Image geschrieben. Laufzeitprozesse brauchen bei einem TLS-intercepting Proxy ebenfalls ihre korrekte Vertrauenskette. Zertifikatsprüfung nicht deaktivieren.
