# Screener-Prüfung vom 08.10.2026

Neuer Produktionsmodus: konkrete bepreiste Angebote unter Nennwert melden; Gebühren, Auszahlungswege und Betreiberkonten sind keine Signalgates. Die publizierten Gebührenmodelle wurden aus der Produktionskonfiguration und die bisherige Aircash-Exit-Recherche aus dem Repo entfernt. Historische Route-Bewertungen bleiben replayfähig.

Ein begrenzter öffentlicher BuySellVouchers-Abruf für Amazon und Abon erfasste **46 Angebote**, erzeugte **17 Arbitrage-Kandidaten** und endete ohne Quellenfehler. Amazon war eine explizite Teilinventur; daraus folgt keine vollständige Anbieterabdeckung. Die Kandidaten bestanden den erneuten Check mit aktuellen Regeln und Quellenstatus. Versand an einen lokalen MemorySink: **17 erfolgreich**, keine Fehler, keine unterdrückten Meldungen. Kein Versand an Telegram, kein Kauf, keine Kontoeinrichtung.

Beispiel aus dem Abruf: 500 USD Amazon-Nennwert für 430 USD, Region US, nominaler Rabatt 14 %. Dies ist ein beobachteter Angebotskandidat, keine bestätigte Barauszahlung oder Gewinnberechnung. Persönliche Verwendbarkeit und Auszahlung entscheidet der Nutzer.

Automatische Regressionen prüfen unbekannte Gebühren, fehlende Auszahlungs-/Kontobelege, reine Prozentangaben ohne Preis, Währungsumrechnung mit datierten ECB-Kursen, Bestandsnull, alte/zukünftige Preise, unterschiedliche Händleridentität, Links mit Zugangsdaten, Deduplizierung, Preiswechsel, erneutes Unterschreiten der Schwelle, Replay sowie erneute Prüfung vor Versand bei Preiswechsel, Quellenfehlern, Alter und Ausverkauf.

Betriebsanleitung: [Compose und Telegram](compose_operation.md). Ohne Bot-Token/Chat-ID gibt es Log-Signale; für dauerndes Tracking muss Worker auf einem dauerhaft verfügbaren Host laufen.

Validierung: **409 bestanden, 2 Live-Tests ausgeschlossen**; Compose-Konfiguration gültig; Docker-Image erfolgreich gebaut. Container-Prüfung mit Python 3.13: Migrationen, Produktionsmodus, simuliertes Rabatt-Signal und entfernte Exit-Gebührenmodelle erfolgreich. Die reale Telegram-Zustellung bleibt bis zur Bot-Konfiguration ungetestet.
