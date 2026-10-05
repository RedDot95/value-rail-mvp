# Live smoke test `dundle` - 2026-10-06

- Start: 2026-10-06 00:41:54 CEST (UTC 22:41:54)
- Ende: 2026-10-06 00:42:13 CEST (Dauer 19.1 s)
- Connector: `dundle` (kind `jsonld_shop`), live_network=True, checkout_quote=False, exit_quote=False
- Capability-Notiz: dundle.com (DE storefront, JSON-LD): configured public product pages, schema.org Product.offers JSON-LD (single seller dundle.com); role price_basis; robots.txt + >=5 s/host + jitter. No checkout quote (dundle FAQ: Servicegebuehr beim Kauf, Hoehe nur im Warenkorb (nicht geoeffnet) -> unknown). parser jsonld-offers/1.0.0
- Scan-Run #2: **ok** - 14 Kandidaten, 14 Bewertungen, 0 Alerts
- Gestoerte Quellen: keine

## HTTP-Requests

| # | URL | Status |
|---|---|---|
| 1 | https://dundle.com/robots.txt | 200 |
| 2 | https://dundle.com/de/paysafecard/ | 200 |
| 3 | https://dundle.com/de/bitsa/ | 200 |
| 4 | https://dundle.com/de/azteco/ | 200 |

## Bewertungen

| Route | Status | Preis | Nennwert | Blockgruende | fehlende Nachweise |
|---|---|---|---|---|---|
| dundle-com-de:de-paysafecard:paysafecard-5-eur-de:dundle-com | Blockiert | 5 EUR | 5 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-10-eur-de:dundle-com | Blockiert | 10 EUR | 10 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-15-eur-de:dundle-com | Blockiert | 15 EUR | 15 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-20-eur-de:dundle-com | Blockiert | 20 EUR | 20 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-25-eur-de:dundle-com | Blockiert | 25 EUR | 25 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-30-eur-de:dundle-com | Blockiert | 30 EUR | 30 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-50-eur-de:dundle-com | Blockiert | 50 EUR | 50 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-75-eur-de:dundle-com | Blockiert | 75 EUR | 75 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-100-eur-de:dundle-com | Blockiert | 100 EUR | 100 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-paysafecard:paysafecard-150-eur-de:dundle-com | Blockiert | 150 EUR | 150 | unknown_required_fee:dundle-com-de_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| dundle-com-de:de-bitsa:bitsa-10-eur:dundle-com | Blockiert | 10 EUR | 10 | unknown_required_fee:dundle-com-de_service_fee, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| dundle-com-de:de-bitsa:bitsa-25-eur:dundle-com | Blockiert | 25 EUR | 25 | unknown_required_fee:dundle-com-de_service_fee, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| dundle-com-de:de-bitsa:bitsa-50-eur:dundle-com | Blockiert | 50 EUR | 50 | unknown_required_fee:dundle-com-de_service_fee, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| dundle-com-de:de-bitsa:bitsa-100-eur:dundle-com | Blockiert | 100 EUR | 100 | unknown_required_fee:dundle-com-de_service_fee, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |

- Angebote (Offer-Snapshots) gespeichert: **14**
- Preisfunde: **0**, verifizierte Routen: **0**
- Seller-Offer-Events: {'baseline': 14, 'new_seller_offer': 0, 'returned': 0, 'price_change': 0, 'gone': 0}
- Letzte Evidence-ID: 55

Ein blockiertes oder unprofitables Ergebnis ist ein korrektes Ergebnis. Es wurde nichts gekauft, kein Checkout/Warenkorb/Konto aufgerufen und keine Sperre umgangen.
