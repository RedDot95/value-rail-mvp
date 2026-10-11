# Deployment

Das Produkt benötigt einen laufenden Docker-Host, HTTPS-Zugriff auf die öffentliche CoinGate-Clearance-Seite und deren Browser-/Suchendpunkte sowie `api.telegram.org` für Push. Start: [Docker Compose](compose_operation.md).

Der Worker scannt alle fünf Minuten. Die Weboberfläche bindet lokal an Port 8000 und verlangt die in `.env` konfigurierten Zugangsdaten. Für externen Zugriff einen TLS-Reverse-Proxy oder privaten Tunnel verwenden. `/livez` prüft den Prozess; `/healthz` prüft Worker, Jobs, Datenalter, Backups und Push-Konfiguration.

Container starten nach Prozessausfällen neu. Ein ausgeschalteter Host führt keine Scans aus. Bestehende Nutzer-Server werden durch Änderungen am Repository nicht automatisch aktualisiert.
