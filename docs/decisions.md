# Aktuelle Architekturentscheidungen

- CoinGate Clearance ist die einzige Marktquelle. Andere Website-Connectoren, Jobs und Rechercheaufnahmen wurden entfernt.
- Die öffentliche Suchliste der Seite wird mit genau deren Clearance-Filter gelesen. Reguläre Angebote werden abgewiesen.
- Signale vergleichen Kaufpreis und Nennwert in derselben Währung. Gebühren, Konten, Budget und Exit-Routen sind keine Scan-Voraussetzungen.
- Spiele/Streaming sind ausgeschlossen; Zahlungs-, Kryptogutscheine und große Händler werden über den Instrumentenkatalog erkannt.
- Identische Stückelungen werden nach Marke, Währung, Länderbeschränkung und Ablaufdatum gruppiert; Preis und Bestand bleiben veränderlich.
- Historische Bewertungen, unveränderliche Regeln und Replay bleiben im Grundgerüst erhalten. Die frühere Route-Engine wird vom Produktions-Scanner nicht verwendet.
- SQLite, Scheduler-Lease, Outbox, Zustellquittungen, Telegram, Weboberfläche und Backups bleiben erhalten.
