# Live smoke test `giftcardwiki` - 2026-10-06

- Start: 2026-10-06 12:47:19 CEST (UTC 10:47:19)
- Ende: 2026-10-06 12:47:26 CEST (Dauer 6.4 s)
- Connector: `giftcardwiki` (kind `gcw_hotdeals`), live_network=True, checkout_quote=False, exit_quote=False
- Capability-Notiz: GiftCardWiki (US, discovery): Hot-Deals-Markenliste (serverseitiges HTML: Marke, Rabatt-%, Kartenanzahl), US-Markt/USD; role discovery_only (Aggregator - nur Hinweise, nie Preisbasis, nie Alert); kein Checkout/Warenkorb/Konto; robots.txt + >=5 s/Host + Jitter; parser gcw-hotdeals/1.0.0
- Scan-Run #265: **ok** - 23 Kandidaten, 23 Bewertungen, 0 Alerts
- Gestoerte Quellen: keine

## HTTP-Requests

| # | URL | Status |
|---|---|---|
| 1 | https://www.giftcardwiki.com/robots.txt | 200 |
| 2 | https://www.giftcardwiki.com/hot-deals/ | 200 |

## Bewertungen

| Route | Status | Preis | Nennwert | Blockgruende | fehlende Nachweise |
|---|---|---|---|---|---|
| giftcardwiki:hot-deals:american-eagle | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:american-girl | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:ann-taylor | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:barnes-noble | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:buca-di-beppo | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:build-a-bear | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:burlington-coat-factory | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:chili-s-restaurants | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:famous-dave-s | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:foot-locker | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:h-m | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:hollister | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:lowe-s | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:mcdonald-s | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:outback-steakhouse | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:papa-johns | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:pottery-barn | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:regal-entertainment | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:steak-n-shake | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:sunglass-hut | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:target | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:tiffany-co | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| giftcardwiki:hot-deals:tory-burch | Blockiert | unknown USD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |

- Angebote (Offer-Snapshots) gespeichert: **23**
- Preisfunde: **0**, verifizierte Routen: **0**
- Seller-Offer-Events: {'baseline': 23, 'new_seller_offer': 0, 'returned': 0, 'price_change': 0, 'gone': 0}
- Letzte Evidence-ID: 6127

Ein blockiertes oder unprofitables Ergebnis ist ein korrektes Ergebnis. Es wurde nichts gekauft, kein Checkout/Warenkorb/Konto aufgerufen und keine Sperre umgangen.
