# Erweiterte Discovery und Teilinventuren (06.10.2026)

CoinGate las bisher nur die erste Suchseite. `payment-cards` für DE meldete 54 Treffer auf drei Seiten; 29 Treffer wurden dadurch nicht abgerufen. Der Produktionsconnector liest jetzt bis zu vier Seiten je konfigurierter Suche. Metadaten, Seitennummer, erwartete Zeilenanzahl und eindeutige Marken müssen zusammenpassen; Fehler auf späteren Seiten bleiben eine Quellenstörung. Ein ausgeschöpftes Seitenbudget ist ausdrücklich eine Teilinventur.

Für tatsächlich von der API gelieferte und vom Instrumentkatalog erkannte Marken werden zusätzlich Stückelungen und veröffentlichte Preise gelesen: höchstens zwölf Detailabfragen je Scan. Das Budget rotiert täglich über die Kandidaten. Inhalt-, Gaming- und Aboangebote werden nicht für diese Detailabfragen ausgewählt. Die exakte API-Markenkennung bleibt erhalten; Klassifizierung ist keine Bestätigung der Einlösung oder Liquidität.

Jede Suchseite hat einen eigenen Antwort-Hash, Byteanzahl und HTTP-Status im Evidenzbeleg. Der übergreifende `body_sha256` einer mehrseitigen Suche ist der Hash des geordneten Seitenbeleg-Manifests; `data_sha256` bindet die strukturierten Antworten sämtlicher gelesener Seiten. Abrufzeitpunkte werden beim Speichern nicht erneuert.

BuySellVouchers bleibt bei konfigurierten Kategoriepfaden ohne Query. Der sichtbare RSC-Block ist oft nur die erste Seite. Nur passende Gesamtanzahl und Einseiten-Metadaten belegen ein vollständiges Inventar. Fehlende Angebote aus einer Teilinventur werden nicht als verschwunden markiert. Erfolgreich gelesene Teilseiten bleiben erfolgreiche Quellenbeobachtungen; Teilinventuren erscheinen im Scanbericht, in gespeicherten Scan-Notizen und auf der Statusseite.

Alle neuen Daten bleiben `aggregator/discovery_only`: keine Preisbasis, kein Checkout, keine bestätigte Auszahlungsquote und kein Gewinnalarm allein aus veröffentlichten Preisen oder Rabatten. Angebots-Snapshots können dieselbe Marke oder Stückelung über mehrere Abrufziele enthalten; ihre Anzahl ist keine Anzahl unabhängiger Arbitrage-Chancen.

Validierung: **370 Offline-Tests bestanden, 2 Live-Tests ausgeschlossen**. Die neuen Regressionstests prüfen spätere Seitenfehler, Budgetgrenzen, unveränderliche Seitenbelege, tägliche Rotation, ausgeschlossene Inhalte und die Verschwunden-Erkennung über mehrere echte Datenbank-Scans.

Öffentlicher Live-Abgleich am 06.10.2026: Die Bitsa-Kategorie bei BuySellVouchers lieferte alle 10 Produkte (eine Seite); die Amazon-Kategorie lieferte nur 20 von 476 Produkten bei 24 gemeldeten Seiten. Letztere wird korrekt als Teilinventur behandelt. Der erste CoinGate-Scan der erweiterten Abfragen speicherte 116 Angebotshinweise aus 126 Kandidaten, 10 außerhalb des Umfangs, keine Quellenfehler und **0 Gewinnalarme**. Dieser Lauf ging der abschließenden täglichen Rotation und der erweiterten Content-Ausschlussliste voraus.

Abschließender Live-Scan mit täglicher Rotation und erweitertem Content-Filter: **138 Angebotshinweise** aus 154 Kandidaten, 16 außerhalb des Umfangs, Scan `ok`, 0 Quellenfehler, **0 belegte profitable Routen und 0 Alarme**. Der Docker-Build sowie der Containerstart mit Migrationen 0001–0005 und verpackter Connector-Konfiguration wurden erfolgreich geprüft.
