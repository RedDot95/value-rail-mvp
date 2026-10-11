# Betrieb

Ein einziger Markt-Job: `coingate_clearance`, alle 300 Sekunden. Zusätzlich tägliches Backup. Keine anderen Händler oder FX-Abfragen.

```bash
docker compose logs --tail 50 worker
docker compose exec worker value-rail health --json
docker compose exec worker value-rail backup
```

Signalschwelle und Preisänderungsschwelle: `config/production.toml`. Push: Telegram-Token und Chat-ID in der lokalen `.env`. Oberfläche: http://localhost:8000.

Ein erfolgreicher leerer Scan bedeutet kein passendes Angebot. Ein fehlgeschlagener Scan bedeutet eine Quellenstörung. Unvollständige Pagination beweist keinen Bestandsverlust. Zustellung prüft Aktualität, Ablauf, Bestand und aktuelle Regeln erneut. Unveränderte Meldungen werden nicht wiederholt; Wiederverfügbarkeit und Bestandszuwachs können neue Meldungen auslösen.

SQLite-Verlauf und Regeln bleiben bei Updates erhalten. Andere Quellen aus alten Datenbanken werden nicht mehr angezeigt oder benachrichtigt. Backups zusätzlich außerhalb des Hosts aufbewahren.

[Start und Updates](compose_operation.md) · [Quelle und Berechnung](sources.md)
