# Liquide Werte: Screener-Ziel und Suchabdeckung (08.10.2026)

Der Produktionsablauf sucht beobachtete Angebote unter Nennwert und meldet Arbitrage-Kandidaten per Telegram. Gebühren-, Auszahlungs- und persönliche Kontoprüfungen sind aus diesem Ablauf entfernt. Es werden keine Käufe oder Kontoanmeldungen ausgelöst. Wohnsitz Deutschland; Konten und Einsatz entscheidet der Nutzer je Angebot.

`config/production.toml` aktiviert `evaluation_mode = "screener"`, den Liquiditäts-Katalogfilter und Alerts für `price_find`. Standard-Signalschwelle: 1 % nominaler Rabatt, frei einstellbar. Diese Meldungen heißen in Oberfläche und Push **Arbitrage-Kandidat**. Sie enthalten keinen berechneten Nettogewinn.

Für einen Kandidaten braucht es einen belegten konkreten Angebotspreis und Nennwert in derselben Währung oder mit aktuellen ECB-Referenzkursen, eine passende Produkt-/Händleridentität und eine aktuelle Beobachtung. Unbekannte Region oder Stückzahl werden angezeigt; Bestand null schließt ein Signal aus. Prozentangaben ohne konkrete bepreiste Stückelung reichen nicht. Veraltete Daten, Quellenfehler und Spiele-/Streamingangebote lösen keinen Versand aus.

Der Katalog enthält 75 Instrumente und Marken, unter anderem Abon/Aircash, Paysafecard, Crypto Voucher, PCS, Flexepin, Cashlib, PayPal-bezogene Produkte, Amazon, Otto und MediaMarkt. 15 Familien haben explizite öffentliche Abrufziele; Kategorie-Sweeps erweitern die Suche. Ein Katalogeintrag bedeutet noch keine Quellenanbindung. Quellen mit Zugriffssperren bleiben deaktiviert. `value-rail coverage --json` meldet beobachtete Kandidaten und tatsächliche Abrufabdeckung.

Direktquellen laufen alle 5 Minuten, übrige aktive Quellen alle 30 Minuten. Pagination und neue Markenabrufe sind begrenzt und rotieren. Teilinventuren markieren nicht beobachtete Angebote nicht als verschwunden. Vollständigkeit über sämtliche Anbieter wird nicht behauptet.

Das Produkt benötigt für Handy-Pushes lediglich Telegram-Konfiguration und für dauerndes Tracking einen laufenden Host; siehe [Compose-Betrieb](compose_operation.md).

Die folgenden Live-Prüfungen vom 06.10.2026 sind historische Quellenprüfungen des damaligen Route-Modus, keine aktuellen Verfügbarkeits- oder Gewinnzusagen.

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

Währungsübergreifende Angebote werden mit öffentlichen täglichen ECB-Referenzkursen verglichen. Originalwährungen bleiben sichtbar; Kurse einschließlich Datum und Antwort-Hash werden mit der Bewertung gespeichert. Ohne passenden gültigen Kurs entsteht kein Signal. Referenzkurse sind keine verbindlichen Umtauschkurse.
