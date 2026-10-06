# Live smoke test `cardbear` - 2026-10-06

- Start: 2026-10-06 12:46:43 CEST (UTC 10:46:43)
- Ende: 2026-10-06 12:47:19 CEST (Dauer 36.0 s)
- Connector: `cardbear` (kind `cardbear_html`), live_network=True, checkout_quote=False, exit_quote=False
- Capability-Notiz: CardBear (US, discovery): Marken-Vergleichsseiten (serverseitige Tabelle: Marktplatz + Rabatt-%), US-Markt/USD, keine Preise; role discovery_only (Aggregator - nur Hinweise, nie Preisbasis, nie Alert); kein Checkout/Warenkorb/Konto; robots.txt + >=5 s/Host + Jitter; parser cardbear-html/1.0.0
- Scan-Run #264: **ok** - 10 Kandidaten, 10 Bewertungen, 0 Alerts
- Gestoerte Quellen: keine

## HTTP-Requests

| # | URL | Status |
|---|---|---|
| 1 | https://www.cardbear.com/robots.txt | 200 |
| 2 | https://www.cardbear.com/gift-card-discount/616/steam | 200 |
| 3 | https://www.cardbear.com/gift-card-discount/606/playstation-network | 200 |
| 4 | https://www.cardbear.com/gift-card-discount/225/google-play | 200 |
| 5 | https://www.cardbear.com/gift-card-discount/853/razer-gold | 200 |
| 6 | https://www.cardbear.com/gift-card-discount/111/amazon | 200 |

## Bewertungen

| Route | Status | Preis | Nennwert | Blockgruende | fehlende Nachweise |
|---|---|---|---|---|---|
| cardbear:playstation-network:cardcenter | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:playstation-network:raise | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:playstation-network:carddepot | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:playstation-network:doordash | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:google-play:doordash | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:google-play:cardcenter | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:google-play:giftcardoutlets | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:amazon:cardcenter | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:amazon:carddepot | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| cardbear:amazon:cardcash | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |

- Angebote (Offer-Snapshots) gespeichert: **10**
- Preisfunde: **0**, verifizierte Routen: **0**
- Seller-Offer-Events: {'baseline': 10, 'new_seller_offer': 0, 'returned': 0, 'price_change': 0, 'gone': 0}
- Letzte Evidence-ID: 6104

Ein blockiertes oder unprofitables Ergebnis ist ein korrektes Ergebnis. Es wurde nichts gekauft, kein Checkout/Warenkorb/Konto aufgerufen und keine Sperre umgangen.
