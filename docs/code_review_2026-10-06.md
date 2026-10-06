> Ergänzung: Lease-Erneuerung/Fencing und serialisierter Versand mit dauerhaften Kanalquittungen sind im Folgepatch umgesetzt. Siehe [Ziel/Abdeckung](liquid_value_scope.md) und [Betrieb](compose_operation.md). Das unten beschriebene At-least-once-Crashfenster bleibt; Engine jetzt 1.4.0; Gebührenbedingungen ersetzen keinen ausführbaren Exit-Quote (siehe [Quote-Import](quote_intake.md)). Die folgenden Testergebnisse beziehen sich auf den ersten Review-Patch.

# Code-Review und Fehlerbehebung – 06.10.2026

Geprüfter Ausgangsstand: `9923717abdbae61efed4406817e78688d16672e6`.
Das Projektziel wurde aus `README.md`, `REVIEW.md`, den Entscheidungsdokumenten
und dem Code rekonstruiert. Frühere Chats waren für dieses Review nicht verfügbar.

## Projektziel

Privates Recherchetool für Gutschein-/Value-Rail-Angebote: Quellen beobachten,
Preise und Evidenz unveränderlich speichern und Kauf → Einlösen/Exit mit
Decimal bewerten. Aggregatoren liefern Discovery-Hinweise. Unbekannte
Pflichtgebühren verhindern verifizierte Routen. Das Tool kauft nichts und
öffnet weder Checkout noch Konten.

Dass laut Übergabedokument alle Live-Routen blockiert sind, ist kein
nachgewiesener Programmfehler: Ohne belegte Pflichtgebühren und Exit-Bedingungen
kann die Engine sie nicht als verifiziert ausweisen.

## Behobene Fehler

| Bereich | Fehler vorher | Verhalten nachher |
|---|---|---|
| Preisbasis | Auswahl nach nacktem Preis, auch bei verschiedenen Währungen/Gebühren | Vergleich belegter All-in-EUR-Preise pro Einheit; frische nutzbare Angebote haben Vorrang |
| FX | Erster FX-Eintrag gewinnt; Alter und nicht positive Kurse werden ignoriert | Neuester passender Kurs; nicht positive Kurse blockieren; benötigte alte Kurse lassen Signale ablaufen |
| Nennwert | Nennwert 0 löst eine Exception aus; negative Werte werden weiterverarbeitet | Nicht positive Nennwerte ergeben `blocked` mit explizitem Grund |
| Quellenstatus | Späterer Teilerfolg überschreibt einen Fehler; Discovery-Fehler lassen bestehenden Status gesund | Gesamter Scan entscheidet über Quellenstatus; bei Teilfehler kein neuer vollständiger Erfolgszeitpunkt |
| Alert-Outbox | Dispatch nur bei Joblauf, dadurch verzögerte/ausbleibende Retries | Jeder Tick des aktiven Schedulers verarbeitet fällige Alerts, auch ohne fällige/aktivierte Jobs |
| Heartbeat | Standby-Worker überschreibt den Heartbeat des aktiven Workers | Nur der Lease-Halter schreibt den gemeinsamen Heartbeat |
| Health | Aggregatoren fehlen in der Zuordnung von Jobs zu Quellen | CoinGate, BuySellVouchers, CardBear und GiftCardWiki werden auf Quellen-Frische geprüft |

Die Engine-Version steigt auf **1.2.0**. FX-Kurse verwenden für die
Frischeprüfung die vorhandene Grenze `max_quote_age_seconds`. Unbenutzte alte
Kurse beeinflussen eine EUR-Route nicht. Feste Gebühren sind gemäß bestehendem
Modell EUR-Beträge; prozentuale Gebühren werden auf die umgerechnete Basis angewandt.

## Validierung

- Ausgangssuite: **254 passed, 2 deselected**.
- Nach den Änderungen: **274 passed, 2 deselected** (vollständige Offline-Suite).
- Regressionstests gegen ursprünglichen Code: **20 failed, 52 passed** in den
  vier betroffenen Testmodulen. Die Fehler betreffen die oben beschriebenen Fälle;
  ein bestehender Heartbeat-Test wurde um die Standby-Prüfung ergänzt.
- `git diff --check` erfolgreich.
- Keine Live-Abfragen an Gutscheinquellen, kein Kauf, kein Deployment.

## Verbleibende Grenzen / weitere Review-Punkte

1. **Scheduler-Lease bei langen Jobs:** Verlängerung erfolgt erst nach einem Job.
   Dauert ein Scan länger als `lock_ttl_seconds`, kann ein zweiter Worker die
   abgelaufene Lease übernehmen. `renew()` wird zudem nicht auf Erfolg geprüft.
   Dafür braucht es laufende Lease-Erneuerung und ein Konzept zum Abbruch/Fencing
   bei Verlust der Lease; dieser Patch ändert die Ausführung laufender Jobs nicht.
2. **Versand ist nicht genau einmal garantiert:** Ein Prozessabbruch nach einem
   erfolgreichen Sink-Aufruf, aber vor Commit von `sent`, führt zum erneuten
   Versand. Auch mehrere unabhängige Dispatcher können dieselbe Pending-Zeile
   lesen. Die stabile `event_id` erlaubt Dedup bei geeigneten Empfängern;
   Telegram bietet hier keine entsprechende atomare Garantie.
3. **Historischer Replay:** Die aktuelle Engine bewertet gespeicherte Inputs
   erneut; alte Engine-Implementierungen werden nicht mitgeführt. Version 1.2.0
   kann bei den korrigierten Randfällen bewusst vom historischen Ergebnis
   abweichen. Gespeicherte Inputs, Ergebnisse und Regeln werden nicht verändert.

Dieses Review enthält gezielte Fehlerbehebungen und Regressionstests, keinen
Nachweis fehlerfreien Dauerbetriebs oder ein vollständiges Sicherheitsaudit.
