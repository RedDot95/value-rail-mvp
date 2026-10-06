# Auszahlungsbelege und Quote-Import (06.10.2026)

Öffentliche Preise dienen der Suche. Für eine belegte profitable Route braucht das System zusätzlich verbindliche, noch gültige Kauf-/Auszahlungsangebote mit allen Gebühren, bestätigter Menge und exakt passender Produktidentität.

## Geprüfte Auszahlungsquellen

| Instrument | Veröffentlichte Kondition | Noch zu belegen |
|---|---|---|
| CASHlib | Bankerstattung; außerhalb des Stornierungszeitraums 15 EUR Gebühr | Land erlaubt, autorisierter Partner, Originalbeleg, unbenutzter voller Saldo vor Ablauf, Identität/Adresse, tatsächlich anwendbare Gesamtgebühren und verbindliche Auszahlung |
| Flexepin EEA | Bankerstattung; außerhalb des Cooling-off-Zeitraums 18 EUR Gebühr | Anwendbare EEA-Bedingungen, zugelassener Händler, Originalbeleg, Saldo/Ablauf, Identität/Adresse, Bankkonto, Gesamtgebühren und verbindliche Auszahlung |
| Neosurf | Guthaben über myNeosurf aufs namensgleiche Bankkonto; KYC bei jeder Erstattung; 5 % Erstattungsgebühr | Gültiger EUR-Saldo, Länder-/Kontoberechtigung, KYC, Bankkonto, tatsächliche Auszahlungskapazität und Gesamtgebühren |

Primärquellen, am 06.10.2026 abgerufen: [CASHlib §§ 8.1–8.9, 20](https://www.cashlib.com/en/terms-and-conditions), [Flexepin EEA §§ 7.3–7.12](https://www.flexepin.com/flexepin-terms-and-conditions-eea/), [Neosurf Refund-FAQ](https://www.neosurf.com/faq/).

Die Produktionsregeln unter Label `liquid-verified-2026-10-06-v2` erfassen diese Gebühren konservativ ohne Annahme einer kostenlosen Widerrufs-/Cooling-off-Erstattung. **Veröffentlichte Bedingungen sind keine ausführbaren Exit-Quotes.** Daher bleibt ihre bestätigte Tiefe `unknown`; rechtliche/vertragliche Tages- und Anfragegrenzen werden ausschließlich als mögliche Obergrenzen im Gebührenbeleg gespeichert. Engine 1.4.0 lässt auch ältere gespeicherte `rule-exit:`-Projektionen nicht mehr als verifizierte Route gelten. Das betrifft ebenso die bestehenden Paysafecard-/Bitsa-Regeln. Alte Datensätze bleiben unverändert; Replay kann deshalb abweichen.

Abon nennt in seinen globalen Bedingungen eine Erstattungsgebühr, verweist aber auch auf länderspezifische Konditionen. Rewarble veröffentlicht SEPA-Gebühren und einen Bank-Auszahlungsweg. Beide bleiben Recherche-Einstiege, bis Variante, Währung, anwendbare Bedingungen und der konkrete Auszahlungsquote belegt sind: [Abon](https://abon.cash/terms-conditions-en/), [Rewarble Gebühren](https://rewarble.com/fees), [Rewarble Bank Transfer](https://rewarble.com/brands/bank).

Bei geprüften Gutschein-Ankäufern sind öffentliche Rechner unverbindlich oder von anschließender Kartenprüfung abhängig. Daraus werden keine garantierten Kaufgebote abgeleitet: [Gutschein Swap OTTO](https://gutschein-swap.de/otto-gutschein-verkaufen/), [Gutscheinplaza Amazon DE](https://www.gutscheinplaza.de/angebot-anfordern/geschenktgutscheine/amazon-de). Keine Gutschein-Codes an Recherchetools oder in das Repository geben.

## Quote-Import

Ein lokaler CLI-Import erlaubt Belege aus bereits zulässig eingeholten Provider-Quotes. Er ruft kein Konto, Checkout, Kauf, Verkauf oder Auszahlungsformular auf und sendet keine Nachrichten. Ohne echte geprüfte Unterlagen lässt sich kein Gewinnweg herstellen.

1. Einen echten, aktuellen Evaluierungsdatensatz auswählen. Die Produktidentität muss vollständig sein; unbekannte Felder werden nicht durch Vermutungen ersetzt. Synthetische Datensätze sind ausgeschlossen.
2. In der privaten Konfiguration `[operator]` mit einem echten Namen und belegten Voraussetzungen einrichten. `reviewed_by` muss diesem Namen entsprechen. Bestehende Voraussetzungen werden beim Import nicht entfernt.
3. Template ausgeben: `value-rail quote-template <evaluation_id> > quotes.json`. Das Template ist absichtlich unvollständig und nicht importierbar.
4. Kauf- und Exit-Quote ausfüllen. Preise/Gebühren als Dezimalstrings, UTC-/Zeitzonenangaben für `captured_at` und `valid_until`, positive bestätigte Menge, vollständige Gebührenliste. Nur wirklich verbindliche Quotes mit `firm: true` und tatsächlich geprüften Gesamtgebühren mit `fees_complete: true` bestätigen.
5. Für jeden Quote die zugehörige, redigierte Belegdatei neben der Manifestdatei aufbewahren. `artifact` ist ein relativer Pfad innerhalb dieses Verzeichnisses; `artifact_sha256` ist der SHA-256 der exakten Datei. Ausbruch über `..`, absolute Pfade und Symlinks außerhalb dieses Verzeichnisses werden abgelehnt.
6. `value-rail import-quotes quotes.json`. Ergebnis: neue immutable Bewertung plus gegebenenfalls Pending-Alert; der Import selbst versendet nichts. Normaler Dispatch prüft Frische, Zulässigkeit und den aktuellen Status der Betreiber-Nachweise erneut. Zurückgezogene oder nicht mehr konfigurierte Voraussetzungen sperren auch ältere Quotes, ohne die Historie umzuschreiben.

Kauf-Quote-Schema, mit absichtlich ungültigen Platzhaltern:

```json
{
  "identity": {"face_value": "100", "face_currency": "EUR", "region": "DE", "variant": "EXAKTE-VARIANTE", "seller": "EXAKTER-VERKAEUFER", "redemption_program": "EXAKTES-PROGRAMM"},
  "source_url": "https://ANBIETER/QUOTE-REFERENZ",
  "source_name": "ANBIETER",
  "unit_price": "unknown",
  "currency": "EUR",
  "quantity": "unknown",
  "captured_at": null,
  "valid_until": null,
  "firm": false,
  "fees_complete": false,
  "fees": [],
  "artifact": "redigierter-beleg.txt",
  "artifact_sha256": "SHA256-DER-DATEI"
}
```

`checkout` und optional `exit` verwenden dieses Schema. Für eine verifizierte Route ist ein verbindlicher Exit zwingend; ohne ihn wird nur eine unvollständige Recherchebewertung gespeichert. `fees: []` ist ausschließlich zulässig, wenn der tatsächlich vollständige Quote keine zusätzlichen Gebühren hat. Unbekannte Pflichtgebühren bleiben blockierend. Der Import bindet Gebührenreferenzen an denselben Belegdateihash. Für Fremdwährungen ohne belegten FX-Kurs entsteht kein verifiziertes Ergebnis.

Geprüfte Routen erhalten den Schlüssel `reviewed:<ursprünglicher-route_key>`. So überschreiben spätere öffentliche Listing-Scans die Quote-Belege nicht. Ursprüngliche Bewertungen und Quote-Zeitpunkte bleiben erhalten; Import eines abgelaufenen Quotes erzeugt keinen neuen Frischebeleg. Kaufmenge und Exit-Tiefe begrenzen die bewertete Menge. Neue Unterlagen für einen inzwischen veränderten öffentlichen Datensatz müssen auf dessen aktuelle Evaluierungs-ID bezogen werden.

**Vertrauensgrenze:** Der benannte Betreiber prüft, ob der Provider, das Angebot, die Gebühren und die Menge echt und ausführbar sind. Ein Dateihash identifiziert einen Beleg, verifiziert aber weder den Aussteller noch den Inhalt. Das System speichert Quote-Daten und Hashreferenzen, nicht den Inhalt der Originaldateien. Redigierte Originalbelege getrennt und dauerhaft sichern; DB-Backups allein sichern diese Dateien nicht. Keine PINs, Zugangsdaten oder unredigierte persönliche Unterlagen importieren.

## Validierung

Die automatisierten Importtests verwenden ausschließlich ausdrücklich synthetische Testbelege und simulierte Provider. Keine Echtgeld-Quotes wurden geliefert oder importiert. Die Tests prüfen atomare Ablehnung, Identitätsbindung, Hashprüfung, Mengenbegrenzung, Replay, Zeitstempel, unbekannte Gebühren, ausgeschlossene synthetische Daten und die Ausgabe der CLI.
