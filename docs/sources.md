# Quellen (Stand Delivery 1)

**Es ist keine einzige Live-Quelle angebunden.** Es wurden keine Endpunkte, Selektoren, APIs oder Checkout-Flows
erfunden. Alle Felder `base_url` stehen auf `"unknown"`, bis ein Zugang tatsächlich verifiziert ist.

## Quellenrollen
| Rolle | Bedeutung | Darf Preisbasis sein? |
|-------|-----------|-----------------------|
| `price_basis` (direct_seller) | Direktverkäufer des identischen Produkts | ja, wenn alle 6 Identitätsfelder passen |
| `discovery_only` (aggregator) | Preisvergleich/Aggregator | **nein** – nur Hinweisgeber; Kaufpreis muss beim Direktverkäufer belegt werden |
| `exit` (exit_venue) | Verkaufs-/Auszahlungsseite | liefert Exit-Quote mit Tiefe |

Aggregatoren sind ausschließlich Discovery (Intervall laut Bauauftrag: täglich). Ein Aggregatorpreis erzeugt nie
einen Rabatt-Alert (Regressionsfall 1).

## Kandidaten-Produktfamilien (Platzhalter)
| Key | Familie | Status | Was für Delivery 2 fehlt |
|-----|---------|--------|---------------------------|
| `bitsa` | Bitsa (Prepaid/Top-up) | **Platzhalter**, `enabled=false`, alle Capabilities `false` (`connectors/placeholders.py`) | Legaler Zugang (API/Partner/ToS-konformes Abrufen), belegbare all-in Checkout-Preise, Gebührenplan, Einlöse-/Exit-Weg in EUR, Account-Voraussetzungen im Operator-Profil |
| `paysafe` | paysafecard | **Platzhalter**, `enabled=false`, alle Capabilities `false` | dito; zusätzlich Mengenlimits pro Kauf/Account (Fall 3 zeigt: angezeigt ≠ kaufbar), Regionsbindung, Einlöseprogramm |

In den Fixtures heißen die Entsprechungen `SYNTHETIC Bitsa-like Reseller` / `SYNTHETIC Paysafe-like Reseller` –
**fiktive** Händler mit fiktiven Preisen, nur zur Prüfung der Logik.

## Connector-Vertrag (für jede künftige Quelle)
`connectors/base.py::Connector`
- `capabilities()` – selbst gemeldet; ein Flag darf nur `true` sein, wenn es gegen eine verifizierte Quelle implementiert ist.
- `discovery(now)` → Routen-Kandidaten (Produktidentität + beteiligte Quellen + Voraussetzungen)
- `offer_fetch(item, now)` → Rohangebote (wirft `SourceUnavailable` bei Störung)
- `normalize(item, raw, now)` → `NormalizedOffer` inkl. Evidenz-Entwürfen
- optional `checkout_quote(item, now)` / `exit_quote(item, now)` → `QuoteBundle` (sonst `CapabilityNotSupported`)
- Der Connector kauft **nie**. `ExecutionResult` ist reine manuelle Buchführung.

## Fixture-Connector
`connectors/fixture.py` liest `tests/fixtures/scenarios/*.json`. Jede Datei muss `"synthetic": true` tragen (sonst
Fehler). Zeitstempel relativ zur Scan-Uhr (`now-60s`, `now-2h`, `now+10m`). Störungen per `--down <source_key>`.
