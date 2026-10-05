# Quellen (Stand 06.10.2026 – Marktplätze/Aggregatoren; darunter Delivery 2 vom 05.10.2026)

## 0. Marktplatz-/Aggregator-Prüfung 06.10.2026 (00:20–00:45 CEST, Box-Egress USA)

Geprüft: robots.txt, AGB/ToS, offizielle API/Affiliate-Feeds, ob Produktseiten ohne Login/JS strukturierte Daten liefern.
UA `ValueRailMVP/0.3 (private price research; polite; honors robots.txt)`. Rohdaten in `research/2026-10-06/` (HTML/XML git-ignoriert).
Browser-Automation steht dem Worker nicht zur Verfügung; Quellen, die sie bräuchten, sind übersprungen.

| Quelle | Rolle | Status | Grund / Beleg |
|---|---|---|---|
| **Recharge.com** (`recharge`) | Direktverkäufer | **live geprüft, deployed** | robots.txt erlaubt Produktseiten (Crawl-delay 1). JSON-LD ProductGroup. Jetzt zusätzlich Seite `/en/de/crypto-voucher` (7 Stückelungen, 5–150 €). `/en/de/azteco` und `/en/de/bitcoin` liefern 404. |
| **dundle.com** (`dundle`, Korsit B.V.) | Direktverkäufer (kein Marktplatz) | **implementiert, offline getestet, live geprüft, deployed** | https://dundle.com/robots.txt: `Allow: /`, sperrt nur /api/, Warenkorb, Zahlung, Konto und `?_rsc=`. AGB https://dundle.com/de/legal/terms-and-conditions/: keine Klausel gegen Crawling, Robots oder Automatisierung. Produktseiten `/de/paysafecard/` (10 Offers, 5–150 €) und `/de/bitsa/` (4 Offers, 10–100 €) haben schema.org `Product.offers[]` mit `priceSpecification` (EUR). Laut FAQ fällt beim Kauf eine Servicegebühr an, deren Höhe nur im Warenkorb steht ⇒ Pflichtgebühr `unknown` ⇒ `blocked`. `/de/azteco/` antwortet 200, aber ohne Product-JSON-LD (derzeit kein Angebot) ⇒ `absent_ok`, 0 Angebote, kein Fehler. |
| **GAMIVO** (`gamivo`) | Marktplatz | **blocked** (Parser implementiert + offline getestet) | robots.txt https://www.gamivo.com/robots.txt erlaubt `/product/*`. T&C https://www.gamivo.com/page/terms-conditions: keine Klausel gegen Robots oder Scraping. Die JSON-LD `Product.offers[]` enthält **je Seller ein Offer mit `seller.name`** (Fixture: 5 Seller auf flexepin-eur-50). **Aber:** Der Worker-Client (Python, HTTP/1.1) bekommt auf jeder Produktseite eine **Cloudflare Managed Challenge** (403, `cf-mitigated: challenge`); nur ein HTTP/2-Client (curl) kam bei der Recherche durch. Protokoll oder Fingerprint zu wechseln, um die Challenge zu vermeiden, wäre eine Umgehung ⇒ **nicht gemacht**. Sitemap gab 403 („Attention Required“). Paysafecard, Bitsa und Azteco wurden auf GAMIVO nicht gefunden (Suche und Kategorie 404). Seiten im Connector: Flexepin 50/100, Neosurf 15, JetonCash 50 (EU). |
| **Eneba** | Marktplatz | **blocked** | robots.txt erlaubt Produktseiten. Die AGB (https://www.eneba.com/terms-and-conditions) werden nur clientseitig per GraphQL gerendert ⇒ ohne JS nicht prüfbar. Das SSR-JSON-LD enthält nur AggregateOffer-Preise **ohne Seller-Namen**. Die Seller-Liste kommt aus der internen GraphQL-API (nicht genutzt). Die Preise sind in USD, weil der Egress in den USA liegt (keine Regionsumgehung). Die offizielle API (https://api.eneba.com/documentation/guide/getting-started) braucht Partner-Credentials und eine IP-Allowlist. |
| **Kinguin** | Marktplatz | **blocked** | AGB https://static.kinguin.net/cms/Kinguin_TC_cbb8b4ce52/Kinguin_TC_cbb8b4ce52.pdf §3.4: „It is forbidden to retrieve the Site Content systematically to create or compile … a collection, compilation, database and catalog (by using robots, …) without written permission from Kinguin.net.“ §3.10 sanktioniert Automatisierungsskripte. |
| **G2A** | Marktplatz | **blocked** | https://www.g2a.com/robots.txt ist von der Box nicht abrufbar (HTTP/2 INTERNAL_ERROR, mit HTTP/1.1 Timeout nach 20 s). Ohne lesbare robots.txt crawlen wir nicht. |
| **CoinsBee** | Direktverkäufer (Zahlung in Krypto) | **blocked** | robots.txt erlaubt die Seiten, die AGB enthalten keine Scraping-Klausel. Die Seiten `/en/gift-cards/payment-cards/paysafecard/`, `…/bitsa/` und `/en/gift-cards/crypto/azteco/` haben JSON-LD aber nur als `AggregateOffer` je Land mit `lowPrice`/`highPrice` (= Nennwertspanne, z. B. EUR 1–150). Der tatsächliche Preis inkl. Aufschlag entsteht erst im Warenkorb (verboten) ⇒ kein belegbarer Preis. |
| **AllKeyShop** | Aggregator (discovery only) | **blocked** | https://www.allkeyshop.com/robots.txt: Der Server schließt die TLS-Verbindung („unexpected eof“), robots.txt nicht lesbar. |
| **GG.deals** | Aggregator (discovery only) | **blocked** | robots.txt (Cloudflare-managed, Content-Signal `search=yes, ai-train=no`) ist lesbar, aber Startseite und https://gg.deals/terms-of-service/ liefern eine **Cloudflare Managed Challenge** (403, `cf-mitigated: challenge`). „GC deals“ war als eigene Quelle nicht auffindbar, gemeint ist wohl GG.deals. |
| **Bitrefill** | Direktverkäufer | **blocked** | Wie am 05.10.: Scraping laut ToS verboten; die Personal API braucht den API-Key des Nutzers. |

**Folgen:**
- Kein Marktplatz mit Seller-Angeboten ist derzeit legal und ohne Umgehung live abrufbar. Der Seller-Offer-Pfad (je Seller eine Route, `seller_offers` und `seller_offer_events`) ist implementiert und mit dem GAMIVO-Fixture offline getestet. Live läuft er für die Direktverkäufer, wo er neue oder entfernte Stückelungen erkennt.
- Aggregatoren: keiner nutzbar ⇒ kein täglicher Aggregator-Job. Der Parser setzt bei `source_kind = "aggregator"` die Rolle `discovery_only`, solche Preise können nie Alerts auslösen.
- Krypto-Watchlist: **Azteco BTC** (eindeutiges Asset) ist nur bei Eneba/Kinguin (blocked) und CoinsBee (kein Preis) gelistet, bei dundle derzeit ohne Angebot (wird im 30-min-Sweep beobachtet). Zusätzlich beobachtet: Recharge **Crypto Voucher**. Dessen Asset wird erst beim Einlösen gewählt, es ist also **kein eindeutiges Asset**; das ist so dokumentiert und es gibt keine Exit-Regel ⇒ `blocked`.

### Generischer JSON-LD-Connector (`kind = "jsonld_shop"`, Parser `jsonld-offers/1.0.0`)
- Liest nur die konfigurierten Produktseiten: kein Crawling, keine Such- oder Sitemap-Seiten, keine internen APIs, nie Warenkorb, Checkout oder Konto.
- Parst schema.org `Product.offers[]`, auch innerhalb von `@graph`, in Listen oder mit `type=` ohne Anführungszeichen. `AggregateOffer` ohne Einzel-Offers zählt nicht als Angebot.
- Seller: bei Direktverkäufern `fixed_seller`, bei Marktplätzen `offer.seller.name` (fehlt der Name ⇒ `ParserBroken`).
- Menge: nur aus `inventoryLevel`, sonst `unknown`.
- Nennwert aus SKU oder Name (z. B. `-50-eur-`, `€50`).
- Eine Route je (Seite, SKU, Seller). Mehrere Offers desselben Sellers werden zusammengefasst: das günstigste wird behalten, die übrigen gezählt (`duplicates`).
- Fehler sind unterscheidbar: 403 ⇒ `AccessDenied` (inkl. Cloudflare-Challenge), 404/5xx ⇒ `UpstreamError`, Layoutbruch ⇒ `ParserBroken`, 0 Offers ⇒ `UnexpectedEmpty`.
- Evidence enthält Parser-Version, JSON-LD- und Body-Hash, das Offer-JSON-LD, ob robots.txt geprüft wurde, und die Quellenrolle.
- Fähigkeiten: `checkout_quote = False`, `exit_quote = False`. Pflichtgebühr `unknown` ⇒ jede Route `blocked`.

### Neue-Seller-Erkennung (`worker/sellers.py`, Migration 0003)
Nach jedem Scan gleicht der Worker alle `seller_offer` gegen die Tabelle `seller_offers` ab. Mögliche Events:
- `baseline`: erste Inventur einer Seite.
- `new_seller_offer`: neues Offer auf einer bereits bekannten Seite.
- `price_change`: Preisänderung.
- `gone`: Offer fehlt, und zwar nur auf einer Seite, die in diesem Scan **erfolgreich** geparst wurde. Eine gestörte Seite ist eine Störung und nie „Seller weg“.
- `returned`: zuvor verschwundenes Offer ist wieder da.

Die Zahlen stehen in `ScanReport.seller_events` und in `health.jobs[].last_scan.seller_events`.


---

# Quellen (Stand Delivery 2, 05.10.2026)

Alle Abrufe am **05.10.2026 zwischen 23:30 und 23:52 CEST** von der Box (curl bzw. dem Connector selbst).
Rohdateien unter `research/2026-10-05/` (Text-Auszüge und robots.txt sind versioniert; große HTML-Rohdateien
sind git-ignoriert und lokal vorhanden). Alle abgerufenen Inhalte wurden als **nicht vertrauenswürdige Daten**
behandelt. Es wurden **keine** Endpunkte oder Selektoren erfunden, keine CAPTCHA/KYC/Regionssperre umgangen,
kein Checkout/Warenkorb/Konto aufgerufen, nichts gekauft.

## 1. Marktplätze: Zugang (maschinenlesbar + erlaubt?)

| Anbieter | robots.txt (abgerufen 05.10.2026) | ToS / API | Ergebnis |
|---|---|---|---|
| **Recharge.com** (Recharge Group / CG Holdings B.V., Teil von Coda Payments) | https://www.recharge.com/robots.txt: `User-agent: *` sperrt `/checkout /cart /orders /user /account /password /api` (erlaubt nur `/api/client/{countries,pages,taxons,products}`), `Crawl-delay: 1`. Produktseiten wie `/en/de/bitsa`, `/en/de/paysafecard` **nicht gesperrt** | Keine Verbraucher-AGB mit Automatisierungsverbot gefunden: `/en/de/terms-and-conditions` u. ä. → 404; Sitemap https://www.recharge.com/sitemap-other.xml listet nur privacy-statement, how-it-works, cookie-statement, accessibility. https://www.recharge.com/en/de/how-it-works enthält keine Automatisierungsklausel. Achtung: die AUP/API-Terms von *getrecharge.com* gehören zu einer **anderen Firma** (Shopify-Abo-App) und sind nicht einschlägig. Die `/api/client/*`-Endpunkte sind **undokumentiert → nicht genutzt** | **Gewählt.** Seiten ohne Login, EUR-Preise, schema.org-JSON-LD (Standard, kein erfundener Selektor) |
| **Bitrefill** | https://www.bitrefill.com/robots.txt: `*` erlaubt; `/buy/` für GPTBot/Claude/Grok-UAs gesperrt | https://www.bitrefill.com/terms/ verbietet „robots, spider or other automated means“ (außer „Agents“). Offizielle **Personal API** https://docs.bitrefill.com/docs/api-overview (Base `https://api.bitrefill.com/v2`, `GET /products`, `/products/search`, `/products/{id}`; Bearer-Key aus `bitrefill.com/account/developers`; Quote 1000 Produkt-Requests/h) | Nur mit **API-Key des Nutzers** zulässig → Kandidat Delivery 3, **Nutzer-Blocker** |
| **Dundle** (→ dundle.com) | https://www.dundle.com/robots.txt: erlaubt außer `/api/`, Warenkorb, Payment | AGB-URL nicht gefunden (geratene Pfade 404) | nicht gewählt: ToS ungeklärt |
| **CoinsBee** | https://www.coinsbee.com/robots.txt: erlaubt (sperrt cart/login u. a.) | `/en/terms` → 404, AGB nicht lokalisiert | nicht gewählt: ToS ungeklärt |
| **Eneba** | https://www.eneba.com/robots.txt vorhanden (Marktplatz mit Dritthändlern) | nicht weiter geprüft | nicht gewählt: Marktplatz/Dritthändler, Identität „Seller“ wechselnd |
| **Kinguin** | https://www.kinguin.net/robots.txt → **403 Access Denied** (Bot-Schutz) | – | ausgeschlossen (keine Umgehung) |
| **G2A** | Verbindung fehlgeschlagen | – | ausgeschlossen |
| **Crypto Voucher** (cryptovoucher.io) | robots.txt → 404-Seite | – | nicht gewählt |
| **Bitnovo** | https://www.bitnovo.com/robots.txt: erlaubt alles | – | Einlösung siehe unten; kein Preis-Feed geprüft |
| **Azteco** | https://azte.co/robots.txt: sperrt nur `/*?*` | – | Einlösung siehe unten |
| **Bitsa (Emittent)** | https://bitsacard.com/robots.txt: erlaubt alles; www.bitsa.com: keine Antwort | – | Quelle für Einlöse-/Exit-Regeln |
| **paysafecard (Emittent)** | https://www.paysafecard.com/robots.txt vorhanden | – | Quelle für Rücktausch-Regeln |

### Recharge.com – was die Seiten liefern (Connector `recharge`, Parser `recharge-jsonld/1.0.0`)
- https://www.recharge.com/en/de/bitsa und https://www.recharge.com/en/de/paysafecard: HTTP 200 ohne Login (CloudFront).
- JSON-LD `ProductGroup` mit `hasVariant[]` → `Product{name, sku ("15-eur"), gtin13, offers{price, priceCurrency, availability, url, priceSpecification: CompoundPriceSpecification[ "Voucher Value", "Service Fee (from)" ]}}`.
- Bitsa DE: 15/25/50/100 EUR, Preis = Nennwert. paysafecard DE: 10/20/30/50/100/150 EUR, Preis = Nennwert, gtin13 `DE_2_PSAFEVAR`.
- „Service Fee (from)“ = 0 ist nur eine **Untergrenze** (zahlungsartabhängig) → im Connector als Pflichtgebühr `unknown`.
- Seitentexte: Bitsa „You will need to live in the EEA to create a BITSA account“, Code 3 Monate gültig; paysafecard „commercial resale of PaysafeCard is forbidden“.
- Antworten setzen Cookies (u. a. mit Client-IP) → **Header/Cookies werden nie gespeichert**; Fixtures enthalten nur `<title>` + JSON-LD (Datei `tests/fixtures/recorded/recharge_com_2026-10-05/`, Original-SHA-256 in `meta.json`).

## 2. Einlösung / Exit pro Familie

### paysafecard (DE)
- AGB DE (Datei „25-05-2026“, Kopfzeile „Version: 06/2025“), https://www.paysafecard.com/en-de/terms-and-conditions/detail/?country=de&tx_pscterms_pi3%5Baction%5D=renderDetail&tx_pscterms_pi3%5Bcontroller%5D=Terms&tx_pscterms_pi3%5Bfilename%5D=L0xlZ2FsL2RlX3BheXNhZmVjYXJkXzI1LTA1LTIwMjYuaHRt&cHash=2114e4e3519f427f8fc1914b2f6df751 (abgerufen 05.10.2026):
  - **5.1** Rücktausch jederzeit auf **persönliches Bankkonto in Deutschland** (IBAN/BIC); nötig: Seriennummer, Restguthaben, Name, E-Mail, Telefon, **Ausweiskopie**, Kopie der PaysafeCard. **Keine Barauszahlung.**
  - **5.3** Identitätsprüfung vor Auszahlung (Geldwäscherecht).
  - **2.1.1** Rücktauschgebühr **5 % des Betrags, max. 5,00 €**. **2.1.2** Bereitstellungsgebühr **3,00 €/Monat nach 30 Tagen**.
  - **3.4** Entgeltliche Übertragung an Dritte verboten; Kauf nur über autorisierte Vertriebsstellen. **6.1** 14 Tage gebührenfreier Rücktritt bei Fernabsatz (konservativ **nicht** angesetzt).
- https://www.paysafecard.com/en-de/fees-limits/ (abgerufen 05.10.2026): Rücktauschgebühr 5 % (max. 5 €); monatliche Gebühr **4 €** nach 30 Tagen (**Widerspruch zu AGB 3 €** – beide dokumentiert, Gebühr nicht angesetzt, Annahme Rücktausch < 30 Tage); max. 50 € pro Zahlung; Auszahlungslimit PaysafeWallet 30.000 €/Jahr.
- Ob Recharge.com eine von paysafecard **autorisierte** Online-Vertriebsstelle ist, ließ sich nicht belegen (Händlerliste lädt dynamisch) → Voraussetzung `paysafecard_seller_authorized_by_psc` = unknown.
- **Folge:** Netto-Exit je Karte = Nennwert − min(5 % · Nennwert, 5 €). Bei Kauf zum Nennwert (Recharge) ist die Route **immer negativ** (50 € → 47,50 €).

### Bitsa
- https://bitsacard.com/en/plans (abgerufen 05.10.2026): Free-Plan max. Guthaben 2.500 €, Aufladung 500 €/Tag · 1.000 €/Monat · 2.500 €/Jahr; **SEPA-Überweisungen 500 €/Tag · 1.000 €/Monat · 2.500 €/Jahr**, Überweisungsgebühr 1 €; Fußnote 6: Überweisung an andere Entität (nicht gleicher Inhaber oder Pecunpay) 1,50 €; **Fußnote 3: „reload fee for voucher redemption may vary between 0% and 6% depending on the transaction“**; Karten: virtuell 2,50 €, physisch 20 €; ATM außerhalb Euro 0,55 € + 1 % (min. 0,75 €), max. 450 €/Tag außerhalb Spaniens.
- https://bitsacard.com/en/card-general-conditions (abgerufen 05.10.2026): Emittent PECUNIA CARDS EDE S.L.U. (Pecunpay); **KYC Pflicht**, automatische Sperre bei unvollständigem/fehlgeschlagenem KYC; Restguthaben-Erstattung bei Kündigung mit Bankbestätigung.
- https://bitsacard.com/en/instructions-redeem-coupon (abgerufen 05.10.2026): Gutschein nicht erstattbar, nicht in bar einlösbar, nicht weiterverkaufbar; 3 Monate gültig.
- **Folge:** EUR-Exit über Kartenguthaben → SEPA grundsätzlich möglich, aber die Einlösegebühr (0–6 %) ist vorab **unbekannt** → verifizierte Route **blockiert**.

### Krypto-Gutscheine (nicht gewählte Familie; keine RuleVersion angelegt)
- **Azteco** On-Chain: https://help.azte.co/article/25-whats-an-azteco-on-chain-voucher (abgerufen 05.10.2026) – 16-stelliger Code, Einlösung auf azte.co an eine **BTC-Adresse** (natives Bitcoin, eindeutiges Asset ohne Contract); Netzwerkgebühren „can cost several dollars“; Lightning-Variante existiert. Kommission steckt im BTC-Betrag, nicht separat in der Primärquelle beziffert.
- **Bitnovo**: https://soporte.bitnovo.com/hc/en-us/articles/13588851414813 (Stand 10.07.2025, abgerufen 05.10.2026) – Gebühren von Bitnovo, Vertriebspartner und Netzwerk, variabel; Nettobetrag erst bei Einlösung sichtbar; Konto + KYC nötig.
- **BTC → EUR** Beispiel: https://www.kraken.com/features/fee-schedule (abgerufen 05.10.2026) – Tier 1 Maker 0,40 % / Taker 0,80 % (zzgl. Auszahlungsgebühr, nicht erhoben).

## 3. Sonstige Primärquellen
- Telegram Bot API `sendMessage`: https://core.telegram.org/bots/api#sendmessage (abgerufen 05.10.2026; `https://api.telegram.org/bot<token>/METHOD_NAME`, Text max. 4096 Zeichen).
- httpx2: https://pypi.org/project/httpx2/ (2.13.1, Autor Tom Christie, Homepage https://github.com/pydantic/httpx2); Starlette TestClient-Doku (https://starlette.dev/testclient/ und https://github.com/Kludex/starlette/blob/main/docs/testclient.md, abgerufen 05.10.2026: „The TestClient is built on httpx2. Plain httpx is still supported, but deprecated“); Starlette Release Notes 1.2.0 (28.05.2026, #3291 / #3323). Siehe `docs/decisions.md` D-24.

## Quellenrollen
| Rolle | Bedeutung | Darf Preisbasis sein? |
|-------|-----------|-----------------------|
| `price_basis` (direct_seller) | Direktverkäufer des identischen Produkts (z. B. `recharge-com-de`) | ja, wenn alle 6 Identitätsfelder passen |
| `discovery_only` (aggregator) | Preisvergleich/Aggregator | **nein** – nur Hinweisgeber |
| `exit` (exit_venue) | Verkaufs-/Auszahlungsseite; auch `rule-exit:<key>` = aus belegter Exit-Regel abgeleitet | liefert Exit-Quote mit Tiefe |

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

## Recharge-Connector (live, opt-in)
`connectors/recharge.py` + `net/http_safe.py`. Standardmäßig **deaktiviert** (`enabled = false`); läuft nur per
`value-rail smoke recharge` oder nach expliziter Aktivierung von Connector + Job `recharge_scan`.
