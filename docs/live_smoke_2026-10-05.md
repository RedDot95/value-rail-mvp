# Live smoke test `recharge` - 2026-10-05

- Start: 2026-10-05 23:48:23 CEST (UTC 21:48:23)
- Ende: 2026-10-05 23:48:35 CEST (Dauer 12.7 s)
- Connector: `recharge` (kind `recharge`), live_network=True, checkout_quote=False, exit_quote=False
- Capability-Notiz: Recharge.com DE product pages, schema.org JSON-LD (robots.txt permits; Crawl-delay honoured). No checkout quote: service fee only 'from 0', payment-method dependent -> unknown/required. parser recharge-jsonld/1.0.0
- Scan-Run #4: **ok** - 10 Kandidaten, 10 Bewertungen, 0 Alerts
- Gestoerte Quellen: keine

## HTTP-Requests

| # | URL | Status |
|---|---|---|
| 1 | https://www.recharge.com/robots.txt | 200 |
| 2 | https://www.recharge.com/en/de/bitsa | 200 |
| 3 | https://www.recharge.com/en/de/paysafecard | 200 |

## Bewertungen

| Route | Status | Preis | Nennwert | Blockgruende | fehlende Nachweise |
|---|---|---|---|---|---|
| recharge-de:bitsa:15-eur | Blockiert | 15 EUR | 15 | unknown_required_fee:recharge_service_fee, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| recharge-de:bitsa:25-eur | Blockiert | 25 EUR | 25 | unknown_required_fee:recharge_service_fee, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| recharge-de:bitsa:50-eur | Blockiert | 50 EUR | 50 | unknown_required_fee:recharge_service_fee, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| recharge-de:bitsa:100-eur | Blockiert | 100 EUR | 100 | unknown_required_fee:recharge_service_fee, unknown_required_fee:bitsa_voucher_reload_fee | checkout_quote, prerequisite:bitsa_account_kyc_eea |
| recharge-de:paysafecard:10-eur | Blockiert | 10 EUR | 10 | unknown_required_fee:recharge_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| recharge-de:paysafecard:20-eur | Blockiert | 20 EUR | 20 | unknown_required_fee:recharge_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| recharge-de:paysafecard:30-eur | Blockiert | 30 EUR | 30 | unknown_required_fee:recharge_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| recharge-de:paysafecard:50-eur | Blockiert | 50 EUR | 50 | unknown_required_fee:recharge_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| recharge-de:paysafecard:100-eur | Blockiert | 100 EUR | 100 | unknown_required_fee:recharge_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |
| recharge-de:paysafecard:150-eur | Blockiert | 150 EUR | 150 | unknown_required_fee:recharge_service_fee | checkout_quote, prerequisite:paysafecard_refund_identity_verification_de_bank_account, prerequisite:paysafecard_seller_authorized_by_psc |

- Angebote (Offer-Snapshots) gespeichert: **10**
- Preisfunde: **0**, verifizierte Routen: **0**
- Letzte Evidence-ID: 88

Ein blockiertes oder unprofitables Ergebnis ist ein korrektes Ergebnis. Es wurde nichts gekauft, kein Checkout/Warenkorb/Konto aufgerufen und keine Sperre umgangen.
