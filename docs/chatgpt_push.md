# ChatGPT-Push

GitHub Actions liest stündlich ausschließlich CoinGate Clearance (Minute 17). Die ChatGPT-Aufgabe prüft die Ergebnisliste stündlich (Minute 45). Ergebnisse: `clearance.json` im Branch `clearance-signals` dieses Repositories. Zugang erfolgt über die bereits verbundene GitHub-App; kein Telegram-Token und kein eigener Server notwendig.

Die Liste enthält nur öffentliche Angebotsdaten: Produkt, Preis, Nennwert, Rabatt, Region, verfügbarer Bestand, Ablaufdatum und Link. Keine Voucher-Codes oder persönlichen Konten. Signal-IDs bleiben bei unveränderten Angeboten stabil; materielle Preisänderungen, Bestandszuwachs und Wiederverfügbarkeit erzeugen neue IDs. Auch bei einem Ausfall bleibt die letzte Signalhistorie erhalten.

Die ChatGPT-Aufgabe meldet nur noch nicht gemeldete IDs aktuell verfügbarer Angebote. Keine Spiele/Streaming, Gebühren oder bestätigten Netto-Renditen. Fehlerberichte und Daten älter als zwei Stunden gelten nicht als frische Treffer. Eine Quellenstörung wird einmal gemeldet statt als leere Trefferliste behandelt.

Der Workflow muss im Standardbranch liegen, damit GitHub den Zeitplan ausführt. Läufe können verzögert sein; das ist keine Echtzeit-Zustellung. Prüfung des Betriebs: GitHub Actions → CoinGate Clearance signal feed und `checked_at`/`status` in der Ergebnisliste. Push-Berechtigungen in ChatGPT und den Handy-Einstellungen müssen aktiviert sein.

Der Docker-Worker und Telegram sind als alternative Betriebsart erhalten. Sie sind für diese ChatGPT-Aufgabe nicht erforderlich.
