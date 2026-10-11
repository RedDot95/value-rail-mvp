# Value Rail – CoinGate Clearance Tracker

Prüft ausschließlich **https://coingate.com/gift-cards/clearance**.

Standardbetrieb: GitHub plant einen Scan alle 30 Minuten und veröffentlicht `clearance.json` auf dem Branch `clearance-signals`. Eine ChatGPT-Aufgabe liest neue Signale und benachrichtigt in der ChatGPT-App. Bei fehlenden frischen Daten fordert sie einen Scan direkt an, statt sich allein auf den GitHub-Zeitplan zu verlassen. Dafür sind kein eigener Server und keine Telegram-Zugangsdaten nötig. Push muss in ChatGPT und auf dem Handy erlaubt sein.

- Meldet konkrete Angebote ab 1 % Rabatt; Schwelle frei einstellbar.
- Filter: Zahlungs-/Kryptogutscheine und Gutscheine großer Händler. Keine Spiele, Streaming- oder Content-Abos.
- Push mit Angebotspreis, Nennwert, Rabatt, Region und Link.
- Neue Angebote, wesentliche Preisänderungen und Wiederverfügbarkeit lösen Meldungen aus. Unveränderte Angebote nicht.
- Gebühren, Auszahlung und Konten prüfst du selbst.

## Optional: eigener Worker

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

`config/production.toml` enthält die einzige Quelle und den optionalen Worker-Scan alle fünf Minuten. Der GitHub-Job ist `.github/workflows/clearance-feed.yml`; Betrieb und Nachabruf sind in `docs/chatgpt_push.md` beschrieben. `config/default.toml` enthält ausschließlich synthetische Offline-Testdaten. Andere Website-Anbindungen sind entfernt. SQLite, Verlauf, Push-Wiederholungen, Backups und Weboberfläche bleiben erhalten.

Tests: `pip install -e '.[dev]'`, anschließend `pytest`.
