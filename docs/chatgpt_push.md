# ChatGPT Push

## Aktueller Ablauf

GitHub Actions liest ausschließlich CoinGate Clearance und veröffentlicht `clearance.json` im Branch `clearance-signals` von `SFS-Labs/value-rail-mvp`. Der Workflow ist zu Minute 17 und 47 geplant. GitHub-Zeitpläne sind Best Effort; diese Konfiguration garantiert keinen halbstündlich frischen Feed.

Die bestehende ChatGPT-Aufgabe **CoinGate Clearance Alarm** prüft zweimal täglich. Sie liest die Datei jedes Mal frisch über die verbundene GitHub-App mit explizitem `ref=clearance-signals`. Sie verwendet keine Websuche und schreibt nichts in GitHub. Sie liest oder verändert `chatgpt-delivery.json` nicht und fordert keine Scans an. Die früher hier beschriebene stündliche, schreibende Refresh-/Zustellbestätigungslogik ist nicht der aktuelle Aufgabenvertrag. Der im Workflow vorhandene manuelle Refresh-Mechanismus ist davon zu unterscheiden.

`CoinGate → GitHub Actions → clearance-signals/clearance.json → ChatGPT-Aufgabe → gegebenenfalls App-Benachrichtigung`

## Wann eine Meldung zulässig ist

Der Feed muss `schema_version=1`, die erwartete CoinGate-Quelladresse, `status=ok` und `enumeration_complete=true` enthalten. `checked_at` muss gültig, nicht zukünftig und höchstens zwei Stunden alt sein. Ein erfolgreicher Workflow allein erfüllt diese Prüfung nicht. Ein veralteter oder fehlerhafter Feed löst keine Angebots- oder Störungs-Push aus.

Nur eine konkret belegte Änderung gegenüber dem letzten tatsächlich zugänglichen erfolgreichen Angebotsbestand löst eine Meldung aus: neues/wieder verfügbares, weggefallenes oder abgelaufenes Angebot sowie Änderungen von Preis, Rabatt, Bestand, Region oder Gültigkeitsende. Ein neuer Prüfzeitpunkt oder identischer Feed löst keine Meldung aus. Ohne verlässliche Vergleichsbasis wird keine Änderung behauptet.

Bei einer belegten Änderung zeigt die Meldung alle aktuell gültigen Treffer, nicht nur neue. Angebote brauchen positive Kaufpreise, Nennwerte und Bestände, übereinstimmende Währungen und eine noch gültige Laufzeit, sofern angegeben. Der nominale Rabatt wird aus ungerundeten Preisen berechnet und muss den Feed-Grenzwert erreichen. Spiele und Streaming-/Content-Abos bleiben ausgeschlossen. Nominalrabatt ist keine Netto-Rendite oder Ausführungsgarantie.

## Betrieb und Nachweis

1. Im [Workflow](https://github.com/SFS-Labs/value-rail-mvp/actions/workflows/clearance-feed.yml) den letzten Lauf, dessen Ergebnis und die tatsächlich veröffentlichte Datei prüfen.
2. In `clearance.json` Zeitstempel, Vollständigkeit und Status getrennt prüfen. Bei einer manuellen Diagnose kann der Owner einmal **Run workflow** auf `master` auslösen; die ChatGPT-Aufgabe tut dies nicht selbst.
3. Aufgabenaktivierung und deren aktuelle Bedingungen prüfen. Keine zweite Aufgabe anlegen und keine Angebote künstlich verändern, um einen Push zu erzeugen.
4. Für einen echten Zustellnachweis braucht es einen erfolgreichen Aufgabenlauf mit belegter Angebotsänderung sowie eine Empfangsbestätigung auf dem vorgesehenen iPhone. Ein Workflow-Erfolg, Connector-Lesezugriff oder erzeugter Chattext beweist den Handyempfang nicht.

Die [Verifikation vom 24. Oktober 2026](operational-demo-2026-10-24.md) trennt Offline-Demo, Live-Feed und noch offenen Handyempfang. ChatGPT- und iOS-Benachrichtigungseinstellungen bleiben Voraussetzungen. Es gibt keine Echtzeit- oder lückenlose Neuheitserkennungsgarantie.

Der Docker-Worker und Telegram sind alternative Betriebsarten; sie werden für die aktuelle ChatGPT-Aufgabe nicht benötigt. Ein Telegram-Token und ein eigener Dauer-Server sind dafür nicht erforderlich.
