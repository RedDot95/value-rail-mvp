# ChatGPT-Push

GitHub Actions liest ausschließlich CoinGate Clearance, geplant zu Minute 17 und 47. Die ChatGPT-Aufgabe prüft die Ergebnisliste stündlich. Ergebnisse: `clearance.json` im Branch `clearance-signals` dieses Repositories. Zugang erfolgt über die bereits verbundene GitHub-App; kein Telegram-Token und kein eigener Server notwendig.

GitHub-Zeitpläne können Läufe verzögern oder auslassen. Ist der Feed fehlerhaft oder älter als eine Stunde, fordert die ChatGPT-Aufgabe deshalb einen neuen Scan an: Sie aktualisiert ausschließlich `chatgpt-delivery.json` mit `refresh_requested_at` und verwendet die Commit-Nachricht `Request CoinGate Clearance refresh`. Dieser Push startet den Scanner direkt. Die Aufgabe wartet begrenzt auf frische Daten und prüft erst danach die Angebote. Zustellbestätigungen starten keine Scans. Der Workflow muss auch auf dem Datenbranch vorhanden sein; die ausgeführte Scanner-Version wird stets aus `master` geladen.

Die Liste enthält nur öffentliche Angebotsdaten: Produkt, Preis, Nennwert, Rabatt, Region, verfügbarer Bestand, Ablaufdatum und Link. Keine Voucher-Codes oder persönlichen Konten. Signal-IDs bleiben bei unveränderten Angeboten stabil; materielle Preisänderungen, Bestandszuwachs und Wiederverfügbarkeit erzeugen neue IDs. Auch bei einem Ausfall bleibt die letzte Signalhistorie erhalten.

Die ChatGPT-Aufgabe meldet nur noch nicht gemeldete IDs aktuell verfügbarer Angebote. Keine Spiele/Streaming, Gebühren oder bestätigten Netto-Renditen. Fehlerberichte und Daten älter als zwei Stunden gelten nicht als frische Treffer. Eine Quellenstörung wird einmal gemeldet statt als leere Trefferliste behandelt.

Der Workflow muss im Standardbranch liegen, damit GitHub den Zeitplan ausführt. Läufe können verzögert sein; das ist keine Echtzeit-Zustellung. Prüfung des Betriebs: GitHub Actions → CoinGate Clearance signal feed und `checked_at`/`status` in der Ergebnisliste. Push-Berechtigungen in ChatGPT und den Handy-Einstellungen müssen aktiviert sein.

Der Docker-Worker und Telegram sind als alternative Betriebsart erhalten. Sie sind für diese ChatGPT-Aufgabe nicht erforderlich.
