# Value Rail – CoinGate Clearance Tracker

Prüft ausschließlich **https://coingate.com/gift-cards/clearance**, alle 5 Minuten.

- Meldet konkrete Angebote ab 1 % Rabatt; Schwelle frei einstellbar.
- Filter: Zahlungs-/Kryptogutscheine und Gutscheine großer Händler. Keine Spiele, Streaming- oder Content-Abos.
- Push mit Angebotspreis, Nennwert, Rabatt, Region und Link.
- Neue Angebote, wesentliche Preisänderungen und Wiederverfügbarkeit lösen Meldungen aus. Unveränderte Angebote nicht.
- Gebühren, Auszahlung und Konten prüfst du selbst.

## Start

In einer lokalen `.env` setzen:

```dotenv
VALUE_RAIL_BASIC_USER=value-rail
VALUE_RAIL_BASIC_PASSWORD=<eigenes-Passwort>
VALUE_RAIL_TELEGRAM_BOT_TOKEN=<Bot-Token>
VALUE_RAIL_TELEGRAM_CHAT_ID=<Chat-ID>
```

```bash
docker compose up -d --build
```

Oberfläche: **http://localhost:8000**. Ohne Telegram-Konfiguration gibt es nur Log-Meldungen. Für laufendes Tracking muss der Rechner eingeschaltet bleiben.

`config/production.toml` enthält die einzige Quelle und den Scan-Job. `config/default.toml` enthält ausschließlich synthetische Offline-Testdaten. Andere Website-Anbindungen sind entfernt. SQLite, Verlauf, Push-Wiederholungen, Backups und Weboberfläche bleiben erhalten.

Tests: `pip install -e '.[dev]'`, anschließend `pytest`.
