# Live smoke test `buysellvouchers` - 2026-10-06

- Start: 2026-10-06 12:46:06 CEST (UTC 10:46:06)
- Ende: 2026-10-06 12:46:42 CEST (Dauer 35.6 s)
- Connector: `buysellvouchers` (kind `bsv_list`), live_network=True, checkout_quote=False, exit_quote=False
- Capability-Notiz: BuySellVouchers (Listen, discovery): Kategorie-Listen /en/products/list/<kat>/ (RSC initialProductsList im HTML, kein Login); Verkaeufer = Store-Name, Einzelverkaeufer pseudonymisiert; Buyer-API braucht Konto+Freigabe (nicht genutzt); role discovery_only (Aggregator - nur Hinweise, nie Preisbasis, nie Alert); kein Checkout/Warenkorb/Konto; robots.txt + >=5 s/Host + Jitter; parser bsv-rsc-list/1.0.0
- Scan-Run #262: **ok** - 48 Kandidaten, 48 Bewertungen, 0 Alerts
- Gestoerte Quellen: keine

## HTTP-Requests

| # | URL | Status |
|---|---|---|
| 1 | https://www.buysellvouchers.com/robots.txt | 200 |
| 2 | https://www.buysellvouchers.com/en/products/list/bitsa-gift-card/ | 200 |
| 3 | https://www.buysellvouchers.com/en/products/list/paysafe-virtual-cards/ | 200 |
| 4 | https://www.buysellvouchers.com/en/products/list/bitnovo-voucher/ | 200 |
| 5 | https://www.buysellvouchers.com/en/products/list/neosurf-voucher/ | 200 |
| 6 | https://www.buysellvouchers.com/en/products/list/Prepaid_Vouchers-Azteco/ | 200 |

## Bewertungen

| Route | Status | Preis | Nennwert | Blockgruende | fehlende Nachweise |
|---|---|---|---|---|---|
| buysellvouchers:bitsa-gift-card:p102874 | Blockiert | 102.56 EUR | 100 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p162173 | Blockiert | 262.71 EUR | 250 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p102873 | Blockiert | 51.53 EUR | 50 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p102884 | Blockiert | 30.77 EUR | 30 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p102875 | Blockiert | 20.61 EUR | 20 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p102879 | Blockiert | 10.31 EUR | 10 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p102880 | Blockiert | 25.65 EUR | 25 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p102881 | Blockiert | 5.16 EUR | 5 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p102883 | Blockiert | 15.39 EUR | 15 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:bitsa-gift-card:p24016 | Blockiert | 57.00 EUR | 50 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:paysafe-virtual-cards:p130013 | Blockiert | 10.51 EUR | 10 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| buysellvouchers:paysafe-virtual-cards:p116264 | Blockiert | 10.40 EUR | 10 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:paysafe-virtual-cards:p116272 | Blockiert | 10.51 EUR | 10 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:paysafe-virtual-cards:p130012 | Blockiert | 5.25 EUR | 5 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| buysellvouchers:paysafe-virtual-cards:p116265 | Blockiert | 26.01 EUR | 25 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:paysafe-virtual-cards:p116267 | Blockiert | 104.01 EUR | 100 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:paysafe-virtual-cards:p130015 | Blockiert | 20.90 EUR | 20 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| buysellvouchers:paysafe-virtual-cards:p116261 | Blockiert | 31.51 EUR | 30 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| buysellvouchers:paysafe-virtual-cards:p116266 | Blockiert | 52.00 EUR | 50 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:paysafe-virtual-cards:p116273 | Blockiert | 26.25 EUR | 25 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:paysafe-virtual-cards:p130016 | Blockiert | 26.25 EUR | 25 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| buysellvouchers:paysafe-virtual-cards:p130018 | Blockiert | 52.26 EUR | 50 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| buysellvouchers:paysafe-virtual-cards:p130014 | Blockiert | 15.76 EUR | 15 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| buysellvouchers:paysafe-virtual-cards:p130019 | Blockiert | 104.52 EUR | 100 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| buysellvouchers:paysafe-virtual-cards:p116274 | Blockiert | 52.26 EUR | 50 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:paysafe-virtual-cards:p116275 | Blockiert | 104.52 EUR | 100 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p102809 | Blockiert | 25.49 EUR | 25 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p102814 | Blockiert | 50.99 EUR | 50 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p102813 | Blockiert | 30.59 EUR | 30 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p102810 | Blockiert | 5.10 EUR | 5 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p102812 | Blockiert | 15.30 EUR | 15 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p102815 | Blockiert | 101.97 EUR | 100 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p116352 | Blockiert | 51.64 AUD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p102811 | Blockiert | 10.15 EUR | 10 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p116351 | Blockiert | 20.55 AUD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p116349 | Blockiert | 102.28 AUD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p116350 | Blockiert | 10.28 AUD | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p116249 | Blockiert | 102.46 GBP | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:GBP | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p116250 | Blockiert | 51.23 GBP | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:GBP | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p116251 | Blockiert | 20.49 GBP | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:GBP | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p116252 | Blockiert | 15.36 GBP | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:GBP | checkout_quote, exit_quote |
| buysellvouchers:neosurf-voucher:p164667 | Blockiert | 14.00 EUR | 20 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| buysellvouchers:prepaid-vouchers-azteco:p160013 | Blockiert | 101.99 USD | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:USD | checkout_quote, exit_quote |
| buysellvouchers:prepaid-vouchers-azteco:p160014 | Blockiert | 50.99 USD | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:USD | checkout_quote, exit_quote |
| buysellvouchers:prepaid-vouchers-azteco:p160015 | Blockiert | 25.99 USD | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:USD | checkout_quote, exit_quote |
| buysellvouchers:prepaid-vouchers-azteco:p160016 | Blockiert | 101.99 USD | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:USD | checkout_quote, exit_quote |
| buysellvouchers:prepaid-vouchers-azteco:p160017 | Blockiert | 50.99 USD | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:USD | checkout_quote, exit_quote |
| buysellvouchers:prepaid-vouchers-azteco:p160018 | Blockiert | 25.99 USD | unknown | direct_price_unverified:only_discovery_only_offers, fx_rate_missing:face_value:USD | checkout_quote, exit_quote |

- Angebote (Offer-Snapshots) gespeichert: **48**
- Preisfunde: **0**, verifizierte Routen: **0**
- Seller-Offer-Events: {'baseline': 48, 'new_seller_offer': 0, 'returned': 0, 'price_change': 0, 'gone': 0}
- Letzte Evidence-ID: 6094

Ein blockiertes oder unprofitables Ergebnis ist ein korrektes Ergebnis. Es wurde nichts gekauft, kein Checkout/Warenkorb/Konto aufgerufen und keine Sperre umgangen.
