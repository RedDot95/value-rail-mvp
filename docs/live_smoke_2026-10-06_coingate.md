# Live smoke test `coingate` - 2026-10-06

- Start: 2026-10-06 12:45:08 CEST (UTC 10:45:08)
- Ende: 2026-10-06 12:46:05 CEST (Dauer 57.1 s)
- Connector: `coingate` (kind `coingate_mcp`), live_network=True, checkout_quote=False, exit_quote=False
- Capability-Notiz: CoinGate Gift Cards (MCP, discovery): offizieller, dokumentierter MCP-Server ohne Login (nur read-only Tools search_gift_cards/get_gift_card; Bestell-/Quote-Tools werden clientseitig verweigert); CoinGate ist selbst Verkaeufer; role discovery_only (Aggregator - nur Hinweise, nie Preisbasis, nie Alert); kein Checkout/Warenkorb/Konto; robots.txt + >=5 s/Host + Jitter; parser coingate-mcp/1.0.0
- Scan-Run #261: **ok** - 60 Kandidaten, 60 Bewertungen, 0 Alerts
- Gestoerte Quellen: keine

## HTTP-Requests

| # | URL | Status |
|---|---|---|
| 1 | https://giftcards-api.coingate.com/robots.txt | 200 |
| 2 | https://giftcards-api.coingate.com/api/mcp | 200 |
| 3 | https://giftcards-api.coingate.com/api/mcp | 200 |
| 4 | https://giftcards-api.coingate.com/api/mcp | 200 |
| 5 | https://giftcards-api.coingate.com/api/mcp | 200 |
| 6 | https://giftcards-api.coingate.com/api/mcp | 200 |
| 7 | https://giftcards-api.coingate.com/api/mcp | 200 |
| 8 | https://giftcards-api.coingate.com/api/mcp | 200 |
| 9 | https://giftcards-api.coingate.com/api/mcp | 200 |

## Bewertungen

| Route | Status | Preis | Nennwert | Blockgruende | fehlende Nachweise |
|---|---|---|---|---|---|
| coingate:card-bitsa-de:41902-5 | Blockiert | 5.35 EUR | 5.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:37245-10 | Blockiert | 10.69 EUR | 10.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:58513-15 | Blockiert | 16.05 EUR | 15.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:31720-20 | Blockiert | 21.39 EUR | 20.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:37246-25 | Blockiert | 26.74 EUR | 25.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:58514-30 | Blockiert | 32.08 EUR | 30.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:31718-50 | Blockiert | 53.47 EUR | 50.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:31719-100 | Blockiert | 105.96 EUR | 100.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:179425-200 | Blockiert | 210.74 EUR | 200.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:46114-250 | Blockiert | 269.9 EUR | 250.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-bitsa-de:303838-range-10 | Blockiert | 10.58 EUR | 10.0 | direct_price_unverified:only_discovery_only_offers, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| coingate:card-paysafecard-de:198728-5 | Blockiert | 5.39 EUR | 5.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| coingate:card-paysafecard-de:74324-10 | Blockiert | 10.48 EUR | 10.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| coingate:card-paysafecard-de:74325-15 | Blockiert | 15.73 EUR | 15.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| coingate:card-paysafecard-de:74326-20 | Blockiert | 20.97 EUR | 20.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| coingate:card-paysafecard-de:74327-25 | Blockiert | 26.21 EUR | 25.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| coingate:card-paysafecard-de:74328-30 | Blockiert | 31.45 EUR | 30.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| coingate:card-paysafecard-de:74329-50 | Blockiert | 52.42 EUR | 50.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| coingate:card-paysafecard-de:74330-100 | Blockiert | 104.83 EUR | 100.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| coingate:card-flexepin-de:29942-10 | Blockiert | 10.33 EUR | 10.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-flexepin-de:29941-20 | Blockiert | 20.65 EUR | 20.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-flexepin-de:29940-30 | Blockiert | 30.98 EUR | 30.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-flexepin-de:29939-50 | Blockiert | 51.63 EUR | 50.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-flexepin-de:29938-100 | Blockiert | 103.25 EUR | 100.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-flexepin-de:41558-150 | Blockiert | 158.7 EUR | 150.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-flexepin-de:29937-200 | Blockiert | 206.5 EUR | 200.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-flexepin-de:29936-250 | Blockiert | 258.13 EUR | 250.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-cashlib-de:16146-5 | Blockiert | 5.33 EUR | 5.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-cashlib-de:31800-10 | Blockiert | 10.54 EUR | 10.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-cashlib-de:31803-20 | Blockiert | 21.07 EUR | 20.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-cashlib-de:31802-50 | Blockiert | 52.69 EUR | 50.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-cashlib-de:31801-100 | Blockiert | 105.37 EUR | 100.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-cashlib-de:40589-150 | Blockiert | 158.48 EUR | 150.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:card-cashlib-de:11483-250 | Blockiert | 262.5 EUR | 250.0 | direct_price_unverified:only_discovery_only_offers | checkout_quote, exit_quote |
| coingate:search-clearance-stock-ww:brand-google-play-sale | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-super | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-paysafecard | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-razer-gold-rixty | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-aircash-a-bon | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-astropay | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-visa-global | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-pcs | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-garena-prepaid-card | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-mastercard-usd | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-wise-usd | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-bitsa | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-epay-eur | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-revolut | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-mastercard | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-onlyfans-global | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-flexepin | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-skrill | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-icash-one-gift-voucher | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-fansly-gift-card | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-tiktok | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-cashlib | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-transcash-mastercard | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-aliexpress-eur | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-wise-gbp | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |
| coingate:search-payment-cards-de:brand-rewarble-advcash-volet-europe | Blockiert | unknown unknown | unknown | no_offer_matching_identity, face_value_unknown | checkout_quote, exit_quote |

- Angebote (Offer-Snapshots) gespeichert: **60**
- Preisfunde: **0**, verifizierte Routen: **0**
- Seller-Offer-Events: {'baseline': 60, 'new_seller_offer': 0, 'returned': 0, 'price_change': 0, 'gone': 0}
- Letzte Evidence-ID: 6011

Ein blockiertes oder unprofitables Ergebnis ist ein korrektes Ergebnis. Es wurde nichts gekauft, kein Checkout/Warenkorb/Konto aufgerufen und keine Sperre umgangen.
