# Live smoke test `gamivo` - 2026-10-06

- Start: 2026-10-06 00:42:14 CEST (UTC 22:42:14)
- Ende: 2026-10-06 00:42:42 CEST (Dauer 27.4 s)
- Connector: `gamivo` (kind `jsonld_shop`), live_network=True, checkout_quote=False, exit_quote=False
- Capability-Notiz: GAMIVO (marketplace, JSON-LD seller offers): configured public product pages, schema.org Product.offers JSON-LD (seller per offer); role price_basis; robots.txt + >=5 s/host + jitter. No checkout quote (GAMIVO: service/payment fees only shown in checkout (not opened) -> unknown). parser jsonld-offers/1.0.0
- Scan-Run #3: **degraded** - 4 Kandidaten, 0 Bewertungen, 0 Alerts
- Gestoerte Quellen: {'gamivo-com': 'gamivo-com: [access_denied_403] HTTP 403 from https://www.gamivo.com/product/jetoncash-card-eur-eu-gift-cards-prepaid-eu-standard-50eur (bot protection/geo block?) - not bypassed'}

## HTTP-Requests

| # | URL | Status |
|---|---|---|
| 1 | https://www.gamivo.com/robots.txt | 200 |
| 2 | https://www.gamivo.com/product/flexepin-eur-50 | 403 |
| 3 | https://www.gamivo.com/product/flexepin-eur-100 | 403 |
| 4 | https://www.gamivo.com/product/neosurf-gift-card-15-eu-eur-prepaid-eu-standard-15eur-gift-cards | 403 |
| 5 | https://www.gamivo.com/product/jetoncash-card-eur-eu-gift-cards-prepaid-eu-standard-50eur | 403 |

## Bewertungen


- Angebote (Offer-Snapshots) gespeichert: **0**
- Preisfunde: **0**, verifizierte Routen: **0**
- Seller-Offer-Events: keine
- Letzte Evidence-ID: 55

Ein blockiertes oder unprofitables Ergebnis ist ein korrektes Ergebnis. Es wurde nichts gekauft, kein Checkout/Warenkorb/Konto aufgerufen und keine Sperre umgangen.

> Nachtrag 06.10.2026 00:50 CEST: Dieser Lauf wurde noch mit der alten Statuslogik als `degraded` gespeichert; seit dem Fix
> (0 Bewertungen + gestörte Quelle ⇒ `failed`) würde er als `failed` geführt. Ergebnis unverändert: alle 4 Produktseiten
> liefern dem Worker-Client (Python http.client, HTTP/1.1) eine Cloudflare-Managed-Challenge (403, `cf-mitigated: challenge`).
> Es wird nicht umgangen ⇒ Quelle `blocked`.
