# Liquide Werte: Ziel und tatsächliche Abdeckung (06.10.2026)

Das Ziel ist die Suche nach vollständig belegten, nach sämtlichen erforderlichen Gebühren profitablen Wegen von Gutscheinen oder Guthaben zu liquidem Wert. Dazu zählen Zahlungs- und Kryptogutscheine sowie handelbare Gutscheine großer Händler. Gaming, Streaming und reine Content-Abos sind aus dem Produktionsumfang ausgeschlossen.

`config/production.toml` aktiviert den Katalogfilter und meldet ausschließlich `verified_route`. Mindestgewinn: 0,01 EUR, Mindest-Edge: 0; der Versand verlangt zusätzlich strikt positiven Gewinn. Nominale Rabatte und Preisfunde bleiben Rechercheergebnisse. Der Offline-Standard und die synthetischen Fixtures behalten ihre bisherigen Regeln.

## Was vorhanden ist

- 75 ausdrücklich **unbewiesene** Instrument-Kandidaten, einschließlich der vom Nutzer genannten Familien. Der Katalog ist erweiterbar; Vollständigkeit oder Liquidität sämtlicher Einträge ist nicht nachgewiesen.
- 15 Familien mit expliziten Abrufzielen; zusätzliche Kategorieabfragen bei CoinGate/GiftCardWiki. BuySellVouchers: 14 überprüfte Kategoriepfade, darunter Abon, PCS, Flexepin, Transcash, Cashlib, PayPal-beschriftete Angebote, OTTO, MediaMarkt und Amazon. CardBear: Amazon statt Gaming.
- CoinGate-Suchen lesen bis zu vier API-Seiten und danach bis zu zwölf zusätzliche, tatsächlich von der API gelieferte, im Katalog erkannte Marken mit Stückelungen/Preisen. Das Detailbudget rotiert täglich über die erkannten Marken, damit spätere Suchtreffer ebenfalls erfasst werden. Budgets begrenzen die Arbeit; die erfassten Daten bleiben `discovery_only`. Pro Seite werden Antwort-Hash, Größe und Status als Beleg gespeichert.
- Unvollständige CoinGate-Suchen und BuySellVouchers-Kategorielisten sind ausdrücklich als Teilinventur markiert; sie können verschwundene Angebote nicht belegen. BuySellVouchers bleibt bei den konfigurierten Pfaden ohne Query. Der Scanbericht und die gespeicherten Scan-Notizen nennen Teilinventuren.
- Anzeige tatsächlicher Beobachtungen, fehlender Nachweise und aktueller profitabler Routen: `value-rail coverage --json`, authentifiziertes `/api/coverage` und `/status`.
- Abon und Aircash, verschiedene Länder/Varianten sowie Rewarble und die Ziel-Wallets bleiben getrennte Produktidentitäten. PayPal-beschriftete Angebote beweisen keinen von PayPal ausgegebenen Guthabengutschein. Multi-Händler-Gutscheine brauchen für jeden Umwandlungsschritt Belege.

## Noch nicht gelöst: ausführbare profitable Exits

Ergänzt: konservative Erstattungsmodelle für CASHlib, Flexepin und Neosurf sowie ein strenger Import geprüfter Quotes. Gebührenbedingungen allein bestätigen keine Auszahlungsmenge und schalten keine Route frei. Details und Primärquellen: [Quote-Belege](quote_intake.md).

Die vorhandenen öffentlichen Connectoren liefern Preise/Discovery; keiner liefert einen vollständigen echten Checkout mit allen Gebühren und eine ausführbare Käuferquote mit ausreichender Tiefe. Die hinterlegten Emittenten-Regeln gelten nur für die exakt passende Variante und alle belegten persönlichen Voraussetzungen. Ein Preis von 100 EUR Nennwert ist kein Beleg für 100 EUR Barauszahlung. Ebenso beweist Wallet-Aufladung keine gebührenfreie Bankauszahlung.

Es gibt derzeit kein belegtes Echtgeld-Betreiberprofil. `[operator]` kann Voraussetzungen mit Status und konkreter `evidence_ref` enthalten. Unbekannte Angaben bleiben unbekannt; synthetische Profile dürfen echte Scans nicht freischalten. Ein Profilname oder eine Zeichenkette allein ist kein unabhängiger Beweis: Der Betreiber muss den referenzierten Nachweis tatsächlich vorhalten und prüfen. Keine Passwörter, persönlichen Unterlagen oder Geheimnisse ins Repository schreiben.

```toml
[operator]
name = "mein-betreiberprofil"
region = "DE"
[operator.capabilities.paysafecard_refund_identity_verification_de_bank_account]
status = "unknown"
evidence_ref = "unknown"
```

Die Engine 1.4.0 verlangt bei echten Routen Referenzen zu Angebots-, Checkout-/Exit-, Gebühren-, FX- und Voraussetzungsbelegen. Alte Pending-Meldungen werden beim Versand mit der aktiven Regelversion erneut bewertet; abgelaufene, unprofitable, inzwischen gestörte, synthetische oder außerhalb des Umfangs liegende Routen werden `suppressed`.

Für einen echten Gewinnalarm fehlen je Route weiterhin aktuelle Preis-/Gebührenbelege, bestätigte Kaufmenge, zulässige Einlösung, ausführbare Auszahlung bzw. Kaufgebot, Exit-Tiefe und persönliche Zugangsvoraussetzungen. Das System beschafft diese nicht durch Käufe oder erfundene Annahmen.

## Live-Prüfung in dieser Sitzung

Frische öffentliche Abfragen vom 06.10.2026, separate Test-DB außerhalb des Repositories:

| Quelle | Ergebnis | Offer-Snapshots | Belegte profitable Routen |
|---|---|---:|---:|
| Recharge DE | robots.txt und 3 Produktseiten erreichbar | 17 | 0 |
| BuySellVouchers | robots.txt und alle 14 Kategoriepfade HTTP 200 | 167 | 0 |
| CoinGate offizielles MCP | öffentliche Produktabfragen erfolgreich | 55 | 0 |

Die Zahlen sind gespeicherte Offer-Snapshots der Testläufe, keine 239 unabhängigen Gewinngelegenheiten. Der anschließende strengere Content-Filter schließt zusätzlich z. B. Rewarble Fansly aus. Es wurde nichts gekauft, kein Konto/Checkout aufgerufen und kein Telegram-Versand ausgeführt. HTTP über den vorgegebenen Proxy verwendet CONNECT zum geprüften öffentlichen Ziel-IP und TLS mit dem ursprünglichen Hostnamen. DNS/IP-Prüfung, Zertifikatsprüfung und Größenlimits bleiben aktiv; gzip/deflate werden auch nach Dekompression begrenzt.

## Katalog

`product_source_found` bedeutet nur, dass eine Produkt-/Programmquelle gefunden wurde. `needs_product_verification` bedeutet, dass bereits das aktuelle Produktangebot noch zu verifizieren ist. **Bei allen Einträgen ist die Liquidität unbewiesen.** Quellen sind Recherche-Einstiege, keine aktuellen Kauf-/Exit-Quotes.

| Instrument | Gruppe | Produktrecherche | Quellen |
|---|---|---|---|
| Abon / A-bon | payment | product_source_found | [Quelle 1](https://abon.cash/) · [Quelle 2](https://abon.cash/terms-conditions-en/) |
| Aircash wallet/card funding | payment | product_source_found | [Quelle 1](https://aircash.eu/aircash-mastercard) |
| PaysafeCard | payment | product_source_found | [Quelle 1](https://www.paysafecard.com/en-gb/) |
| Neosurf | payment | product_source_found | [Quelle 1](https://www.neosurf.com/neosurf-voucher/) |
| Flexepin | payment | product_source_found | [Quelle 1](https://www.flexepin.com/faq/) |
| CASHlib | payment | product_source_found | [Quelle 1](https://cashlib.com/) |
| CashtoCode eVoucher | payment | product_source_found | [Quelle 1](https://cashtocode.com/) · [Quelle 2](https://cashtocode.com/help/cashtocode-evoucher-refund) |
| MiFinity eVoucher | payment | product_source_found | [Quelle 1](https://mifinity.com/evoucher/) |
| MuchBetter Cash Voucher | payment | product_source_found | [Quelle 1](https://muchbetter.com/en/muchbetter-voucher) |
| AstroPay / Larstal prepaid voucher | payment | product_source_found | [Quelle 1](https://getapp.astropaycard.com/terms-and-conditions/voucher.html) |
| ecoVoucher | payment | product_source_found | [Quelle 1](https://baxity.com/ecovoucher-vs-jetoncash-astropay-neosurf) |
| JetonCash | payment | product_source_found | [Quelle 1](https://blog.jeton.com/what-is-jetoncash) · [Quelle 2](https://www.seagm.com/en-us/jetoncash-voucher-europe) |
| Bitsa reload voucher | card_reload | product_source_found | [Quelle 1](https://bitsacard.com/en/general-terms-and-conditions) |
| PCS Mastercard reload | card_reload | product_source_found | [Quelle 1](https://www.mypcs.com/tarifs/) · [Quelle 2](https://www.mypcs.com/en/besoin-daide/my-transactions-and-transfers/top-up-my-pcs-card/top-up-my-pcs-card-by-top-up-voucher/) |
| Transcash reload | card_reload | product_source_found | [Quelle 1](https://www.transcash.fr/en/prepaid-card/) · [Quelle 2](https://www.transcash.fr/pdf/tableau_des_frais_transcash.pdf) |
| Toneo First reload | card_reload | product_source_found | [Quelle 1](https://www.toneofirst.com/en/toneofirst-offers-services/mastercard-by-toneofirst/subscriptions/) |
| Crypto Voucher | crypto | product_source_found | [Quelle 1](https://cryptovoucher.io/redeem-now) |
| Azteco on-chain / Lightning | crypto | product_source_found | [Quelle 1](https://azte.co/en/bitcoin-vouchers) |
| Bitnovo coupon | crypto | product_source_found | [Quelle 1](https://www.bitnovo.com/en/instructions/coupons) |
| Binance Gift Card | crypto | product_source_found | [Quelle 1](https://www.binance.com/en-GB/gift-card) |
| Bitcoinbon | crypto | needs_product_verification | offen |
| Rewarble general voucher | wallet_reload | product_source_found | [Quelle 1](https://rewarble.com/redeem) · [Quelle 2](https://rewarble.com/fees) |
| Rewarble → PayPal | wallet_reload | product_source_found | [Quelle 1](https://rewarble.com/brands/paypal) · [Quelle 2](https://rewarble.com/fees) |
| Rewarble → Skrill | wallet_reload | product_source_found | [Quelle 1](https://rewarble.com/brands/skrill) · [Quelle 2](https://rewarble.com/fees) |
| Rewarble → Neteller | wallet_reload | product_source_found | [Quelle 1](https://rewarble.com/brands/neteller) · [Quelle 2](https://rewarble.com/fees) |
| Rewarble → Revolut | wallet_reload | product_source_found | [Quelle 1](https://rewarble.com/brands/revolut) · [Quelle 2](https://rewarble.com/fees) |
| Rewarble → Wise | wallet_reload | product_source_found | [Quelle 1](https://rewarble.com/brands/wise) · [Quelle 2](https://rewarble.com/fees) |
| Rewarble → Bank transfer | wallet_reload | product_source_found | [Quelle 1](https://rewarble.com/brands/bank) · [Quelle 2](https://rewarble.com/fees) |
| PayPal-labelled voucher (issuer unverified) | wallet_reload | product_source_found | [Quelle 1](https://www.paypal.com/us/cshelp/article/how-do-i-buy-and-send-a-digital-gift-card-through-paypal-help322) |
| Amazon | retail | product_source_found | [Quelle 1](https://www.amazon.de/-/en/gp/help/customer/display.html?nodeId=GG2R4MGPKZQJEG7B) |
| OTTO | retail | product_source_found | [Quelle 1](https://gutschein-swap.de/otto-gutschein-verkaufen/) |
| MediaMarkt | retail | product_source_found | [Quelle 1](https://www.mediamarkt.de/de/specials/geschenkkarte) |
| Saturn | retail | product_source_found | [Quelle 1](https://hilfe.saturn.de/app/answers/detail/a_id/6360/) |
| IKEA | retail | product_source_found | [Quelle 1](https://www.ikea.com/de/de/gift-cards/) |
| Zalando | retail | product_source_found | [Quelle 1](https://en.zalando.de/giftvouchers/) |
| Douglas | retail | product_source_found | [Quelle 1](https://www.douglas.de/Geschenke/Geschenkgutschein/index_0809.html) |
| dm-drogerie markt | retail | product_source_found | [Quelle 1](https://www.dm.de/services/services-im-markt/geschenkkarten-3480686) |
| ROSSMANN | retail | product_source_found | [Quelle 1](https://rossmann-gutscheine.de/) |
| Conrad | retail | product_source_found | [Quelle 1](https://www.wunschgutschein.de/pages/partnershops) |
| Cyberport | retail | product_source_found | [Quelle 1](https://www.wunschgutschein.de/pages/partnershops) |
| Sephora | retail | product_source_found | [Quelle 1](https://www.wunschgutschein.de/pages/partnershops) |
| Rituals | retail | product_source_found | [Quelle 1](https://www.wunschgutschein.de/pages/partnershops) |
| OBI | retail | product_source_found | [Quelle 1](https://www.wunschgutschein.de/pages/partnershops) |
| Dehner | retail | product_source_found | [Quelle 1](https://www.wunschgutschein.de/pages/partnershops) |
| REWE | retail | needs_product_verification | offen |
| EDEKA | retail | needs_product_verification | offen |
| Kaufland | retail | needs_product_verification | offen |
| Lidl | retail | needs_product_verification | offen |
| ALDI | retail | needs_product_verification | offen |
| H&M | retail | needs_product_verification | offen |
| C&A | retail | needs_product_verification | offen |
| Decathlon | retail | needs_product_verification | offen |
| Thalia | retail | needs_product_verification | offen |
| Tchibo | retail | needs_product_verification | offen |
| BAUHAUS | retail | needs_product_verification | offen |
| HORNBACH | retail | needs_product_verification | offen |
| toom | retail | needs_product_verification | offen |
| Breuninger | retail | needs_product_verification | offen |
| GALERIA | retail | needs_product_verification | offen |
| ABOUT YOU | retail | needs_product_verification | offen |
| Peek & Cloppenburg | retail | needs_product_verification | offen |
| Apple Store hardware gift card | retail | needs_product_verification | offen |
| INTERSPORT | retail | needs_product_verification | offen |
| WUNSCHGUTSCHEIN | multi_merchant | product_source_found | [Quelle 1](https://www.wunschgutschein.de/) · [Quelle 2](https://www.wunschgutschein.de/pages/einloesebedingungen-ware) |
| cadooz BestChoice | multi_merchant | product_source_found | [Quelle 1](https://www.cadooz.com/bestchoice-universalgutschein/) |
| ShoppingCARD | multi_merchant | needs_product_verification | offen |
| Shell | fuel | needs_product_verification | offen |
| Aral | fuel | needs_product_verification | offen |
| Esso | fuel | needs_product_verification | offen |
| TotalEnergies | fuel | needs_product_verification | offen |
| Deutsche Bahn | transport | needs_product_verification | offen |
| Uber | transport | needs_product_verification | offen |
| FlixBus | transport | needs_product_verification | offen |
| Airbnb | travel | needs_product_verification | offen |
| Booking.com | travel | needs_product_verification | offen |
