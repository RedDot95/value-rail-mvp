# CoinGate Clearance – Prüfung 10.10.2026

Frischer vollständiger Abruf um 23:04 UTC: 811 Clearance-Codes, 31 passende Angebotsgruppen, 31 Rabatt-Signale ab 1 %. Alle 31 bestanden die erneute Versandprüfung und wurden einem lokalen Memory-Test-Sink zugestellt. Kein Versand an Telegram und keine Käufe.

Beispiel: Paysafecard 10 EUR, Kaufpreis 8,4246627 EUR, nominaler Rabatt 15,753373 %, Region BE, 16 Codes zum beobachteten Mindestpreis. Das ist ein Preisfund vor Gebühren und keine bestätigte Netto-Rendite.

Die Suchliste stammt direkt aus dem öffentlichen Browser-Client der verlinkten Clearance-Seite. Filter: `provider:resale AND resale_listable:true`. Regulärer Produktbestand wird nicht abgefragt. Nullable Datumsfelder werden von dieser API teils als `{}` statt `null` geliefert; das ist in Parser und Regressionstests berücksichtigt.

Offline geprüft: Clearance-Filter, vollständige/partielle Pagination, ungültige Preise und Identitäten, Ausschluss von Spielen/Streaming, Ablauf, Bestand, Deduplizierung, Preisänderungen, Wiederverfügbarkeit, Unterdrückung alter Anbieter-Meldungen und historischer Replay. Die automatischen Tests kontaktieren keine externen Anbieter.

Validierung: 323 Offline-Tests bestanden, Compose-Konfiguration gültig, Docker-Image erfolgreich gebaut; Python-3.13-Container mit Migration, Produktions-Registry, Offline-Scan und Web-Initialisierung geprüft. Telegram auf einem Nutzer-Handy und Dauerbetrieb auf einem Nutzer-Host sind noch nicht geprüft.
