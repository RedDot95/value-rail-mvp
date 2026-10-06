> Update 06.10.2026: BuySellVouchers unterstützt jetzt normale, robots-erlaubte `?page=N`-Navigation mit Budget und täglicher Rotation (`bsv-rsc-list/1.2.0`). Die frühere Schlussfolgerung „nur Pfade ohne Query“ war zu streng: die spezifische Allow-Regel gewinnt. Ein öffentlicher Abruf von Amazon-Seite 2 bestätigte HTTP 200, `currentPage=2` und weitere 20 Produkte. Details und Grenzen: [Pagination](discovery_pagination.md). Die folgenden früheren Smoke-Zahlen bleiben historische Einzelmessungen.

# Quellen (Stand 06.10.2026 – Marktplätze/Aggregatoren inkl. Vergleichsseiten 12:47 CEST, TypeSafe 13:14 CEST; darunter Delivery 2 vom 05.10.2026)

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
- Aggregatoren (Stand 00:45): keiner nutzbar. **Update 12:47 CEST:** siehe Abschnitt 0b. CoinGate (offizieller MCP), BuySellVouchers, CardBear und GiftCardWiki laufen jetzt als tägliche Discovery-Jobs (`discovery_only`, nie Alert). GCX und GG.deals sind blocked.
- Krypto-Watchlist: **Azteco BTC** (eindeutiges Asset) ist nur bei Eneba/Kinguin (blocked) und CoinsBee (kein Preis) gelistet, bei dundle derzeit ohne Angebot (wird im 30-min-Sweep beobachtet). Zusätzlich beobachtet: Recharge **Crypto Voucher**. Dessen Asset wird erst beim Einlösen gewählt, es ist also **kein eindeutiges Asset**; das ist so dokumentiert und es gibt keine Exit-Regel ⇒ `blocked`.

## 0b. Aggregator-/Vergleichsseiten 06.10.2026 (12:29–12:47 CEST, Box-Egress USA)

Auftrag: sechs Vergleichs- und Aggregatorseiten als **Discovery-Quellen** prüfen. Geprüft wurden jeweils robots.txt, AGB/ToS, ob es eine offizielle API oder einen Feed gibt, und ob die Seiten ohne Login und ohne JS strukturierte Daten liefern.
Rohdaten liegen in `research/2026-10-06/aggregators/`. Abgerufen wurde mit dem SafeHttpClient: UA `ValueRailMVP/0.3`, nur https, Host-Allowlist, Public-IP-Pinning, ≥ 5 s pro Host + Jitter.

**Grundsatz:** Alle integrierten Quellen sind im Code fest auf `kind = aggregator` und `role = discovery_only` gesetzt (Klassenkonstante; die Config hat dafür kein Feld, `extra = forbid`).
Ein Aggregatorpreis ist nur ein **Hinweis**:
- Er ist nie Preisbasis, nie Preisfund und nie Alert. Die Engine blockt mit `direct_price_unverified:only_discovery_only_offers`; bei reinen Rabatt-Leads greift schon vorher `face_value_unknown`.
- Zusätzlich hängt an jedem Lead eine Pflichtgebühr `unknown`.
- **Eine verifizierte Route kann aus diesen Quellen allein nie entstehen.** Vorher muss ein price_basis-Connector den Direktpreis beim Verkäufer belegen.

| Quelle (Prüf-URL) | Status | robots.txt / AGB / API (Abruf 06.10.2026) | Daten | Integration |
|---|---|---|---|---|
| **CoinGate Gift Cards**: https://coingate.com/gift-cards/clearance?country%5B0%5D=WW&country%5B1%5D=DE&page=2 | **zugänglich über die offizielle API ⇒ integriert** (`coingate`, `kind = coingate_mcp`, Parser `coingate-mcp/1.0.0`) | **Web:** https://coingate.com/robots.txt sperrt u. a. `/*?country=*`, `/checkout/` und `*/feed*`; es gibt zwei `User-agent: *`-Gruppen (siehe Robots-Fix unten). Die Clearance-Seite liefert zwar 200, die Produktliste wird aber clientseitig gerendert (kein JSON-LD, im RSC nur Navigation) ⇒ der Web-Pfad wird **nicht** genutzt, auch keine Country-Filter-URLs. **Offizieller Weg:** https://coingate.com/gift-cards/mcp und `llms.txt` dokumentieren einen kostenlosen MCP-Server **ohne Login/API-Key**: `https://giftcards-api.coingate.com/api/mcp` (Streamable HTTP, JSON-RPC, Protokoll 2025-06-18, zustandslos). Dessen robots.txt: `User-agent: * / Disallow:` (alles erlaubt). Gift-Card-AGB https://coingate.com/gift-cards/terms-and-conditions (Stand 31.03.2025, UAB Rewards Distributed): keine Robots- oder Scraping-Klausel; der Weiterverkauf gekaufter Karten ist untersagt. Das Business-API (https://www.gifq.com/platform/api) braucht ein Business-Konto ⇒ nicht genutzt. | Über `get_gift_card(brand, country)`: Produkte mit `gift_card_id`, Stückelung, **EUR-Preis**, Lagerbestand, Region und `clearance_offers[]`. Über `search_gift_cards(category, country)`: Marken mit `max_discount_percent`. Die Kategorie **`clearance-stock`** ist die Clearance-Liste: am 06.10. für DE **0 Treffer**, für WW 1 Treffer (Google Play SALE, 20 %, in WW nicht auf Lager). **CoinGate verkauft selbst** (UAB Rewards Distributed); es gibt keinen Fremd-Seller. Der Link zeigt auf die eigene Produktseite. Preise im Smoke (12:45 CEST): Bitsa DE 5–250 € mit 5,4–8,0 % **Aufschlag**, Paysafecard DE mit 4,8–7,8 %, Flexepin DE mit 3,25–5,8 %, CASHlib DE mit 5,0–6,6 %. Kein Rabatt auf die Zielfamilien. | Ziele: get_gift_card für bitsa, paysafecard, flexepin und cashlib (jeweils DE); search_gift_cards für clearance-stock DE und WW (`empty_ok`: explizit 0 Treffer ist eine Beobachtung, keine Störung) sowie payment-cards DE. Der Client ruft nur die Tools `search_gift_cards`, `get_gift_card` und `list_categories` auf. `quote_order`, `create_order`, `get_order`, `notify_when_in_stock` und `list_payment_methods` sowie jedes `email`-Argument werden mit `PermissionError` verweigert. Es werden keine Cookies gesendet und nur die Protokoll-Header `mcp-protocol-version`/`mcp-session-id` erlaubt. |
| **CardBear**: https://www.cardbear.com/ | **zugänglich ⇒ integriert** (`cardbear`, `cardbear_html`, Parser `cardbear-html/1.0.0`), US-Markt | https://www.cardbear.com/robots.txt sperrt nur `/r.php` (Outbound-Redirector) und `/emailalert.php`. AGB https://www.cardbear.com/terms (gültig ab 15.07.2026): „personal, non-commercial comparison … Do not … scrape at unreasonable volume … Automated access, API use, or data reuse should be reasonable and must not disrupt CardBear or misrepresent CardBear data“ ⇒ maßvoller automatisierter Zugriff ist ausdrücklich zulässig. Es gibt keine offizielle API. JSON-LD enthält nur Organization/WebSite/Product mit `AggregateOffer` (nur `offerCount`, kein Preis). | Pro Marke (Sitemap: 981 Markenseiten) eine serverseitige Tabelle: **Marktplatz** (CardCash, Cardcenter, Carddepot, Raise, DoorDash, …) mit **Rabatt-%** und Schutz. **Keine Preise, kein Nennwert, USD/US-Karten**, keine EU-Produkte, kein paysafecard/Bitsa. Der Seller-Link läuft über `/r.php?storeid=…&giftstore=…`: er wird nur gespeichert, **nie aufgerufen** (robots-gesperrt). | 5 Markenseiten: Steam, PlayStation Network, Google Play, Razer Gold, Amazon (alle US). Smoke: 10 Leads, z. B. PSN bei Cardcenter 15,8 %, Raise 12,6 %, Carddepot 12 %; Google Play bei DoorDash 10 %. Steam und Razer Gold hatten keinen Marktplatz auf Lager (in den Notes). |
| **GiftCardWiki**: https://www.giftcardwiki.com/ | **zugänglich ⇒ integriert** (`giftcardwiki`, `gcw_hotdeals`, Parser `gcw-hotdeals/1.0.0`), US-Markt | https://www.giftcardwiki.com/robots.txt sperrt `/buy/`, `/sell/` und `/club/`. ToS https://forum.giftcardwiki.com/t/terms-of-service/4 (Discourse, Stand 31.05.2015, CC-BY-SA): keine Scraping- oder Robots-Klausel. Es gibt keine offizielle API; `/api/v1/gift-cards/search-hints/` ist intern und wird nicht genutzt. Die Karten-Tabellen sind JS (Handlebars). | `/hot-deals/` serverseitig: **Marke, Rabatt-%, Kartenanzahl** und ein Link auf `/gift-cards/<Marke>`. Kein Preis, kein Nennwert, **kein Verkäufer** im HTML (Marktfilter CardCash/CardCookie/GiftCardSaving nur als Zähler). Nur US-Händler (Restaurants, Retail). | Nur 1 Seite pro Tag. Smoke: 23 Marken, z. B. Steak n Shake 33,4 %, Buca di Beppo 25 %, Build-A-Bear 24 %. |
| **GCX (Raise)**: https://gcx.app/ | **blocked** | https://gcx.app/robots.txt sperrt `/cart`, `/checkouts`, `/users` und Query-Parameter. **AGB https://gcx.app/terms (Raise Marketplace, LLC, „Last Updated: June 15, 2026“)**: Abschnitt (c) verbietet „any automated or non-automated means of data gathering, data mining or extraction … including any use of "robots", "scrapers", "spiders"“; Abschnitt (h) verbietet „Aggregate or scrape any content … without our express written permission“. Außerdem ist die Startseite eine reine JS-SPA (777 Byte, „You need to enable JavaScript to run this app“), über plain HTTP kommen keine Daten. | – | **nicht integriert** (`gcx`, `kind = blocked`). Für eine Nutzung bräuchte es eine schriftliche Erlaubnis von Raise. |
| **BuySellVouchers**: https://hub.buysellvouchers.com/ | **zugänglich (Listen-Seiten) ⇒ integriert** (`buysellvouchers`, `bsv_list`, Parser `bsv-rsc-list/1.0.0`); **offizielle Buyer-API braucht den Nutzer** | hub: robots.txt `Allow: /`, reine Landingpage. www: https://www.buysellvouchers.com/robots.txt hat `Allow: /*?page=` und `Disallow: /*?`, sperrt außerdem `/*/products/buy/`, `processPayment`, `feedbacks/show` und `getDescription` ⇒ **nur Kategorie-Pfade ohne Query**. AGB https://www.buysellvouchers.com/en/terms-and-conditions/ (Stand 01.09.2026, Overmorrow Trading Solutions OPC): keine Robots- oder Scraping-Klausel. §13.1 untersagt die unbefugte Nutzung von Plattform-IP (wir veröffentlichen nichts, private Preisrecherche); §4.5/§9.1.3 verbieten VPNs (wir nutzen keine). **Buyer-API** https://hub.buysellvouchers.com/giftcard-api/: braucht ein bestehendes Käuferkonto und eine Zugangsprüfung, „no public self-serve signup“ ⇒ **nur durch den Nutzer**. | `/en/products/list/<Kategorie>/` liefert im HTML den RSC-Payload `initialProductsList`: je Angebot Name, **EUR-Preis**, Menge, verkauft, `discount_percent_pub`, Aktivierungsregion/-land und **Verkäufer** (öffentlicher Store-Name, z. B. EliteLoops; Einzelverkäufer ohne Store werden zu `bsv-seller-<hash>` pseudonymisiert). Kein Kauf-Link wird aufgerufen. Smoke (12:46 CEST): Bitsa EU 5–250 € bei EliteLoops mit 2,6–5,1 % Aufschlag (ein Einzelverkäufer: 50 € für 57 €); **Paysafe DE/FR/ES** 5–100 € bei EliteLoops mit 4,0–5,1 % Aufschlag; Neosurf EU/GB mit 1,5–2,5 % Aufschlag; Azteco (USD) mit 2–4 % Aufschlag. Auffällig: **Neosurf 20 € für 14,00 € (30 %)** von einem Einzelverkäufer mit Menge 2 und 0 Verkäufen. Das ist nur ein Hinweis mit hohem Marktplatzrisiko. `bitnovo-voucher`: explizit 0 Produkte. | 5 Kategorien: bitsa-gift-card, paysafe-virtual-cards, bitnovo-voucher (`empty_ok`), neosurf-voucher, Prepaid_Vouchers-Azteco. `Paysafecard-virtual-cards` ist leer, die Angebote liegen unter `paysafe-virtual-cards`. |
| **GG.deals**: https://gg.deals/prepaids/?regions=de,eu | **blocked** | robots.txt (Cloudflare-managed, `Content-Signal: search=yes,ai-train=no,use=reference`, `Allow: /`) ist lesbar. **Die Prüf-URL antwortet mit HTTP 403, `cf-mitigated: challenge`, `server: cloudflare`** (Cloudflare Managed Challenge, erneut geprüft am 06.10.2026 ca. 12:31 CEST). | – | **nicht integriert** (`ggdeals`, `kind = blocked`). Die Challenge wird nicht umgangen: kein anderer Client, kein UA-Wechsel, kein Browser. |

**Brauchen den Nutzer:** BuySellVouchers Buyer-API (Konto + Freigabe); CoinGate/GIFQ Business-API (Business-Konto; nicht nötig, weil der MCP-Server frei ist); GCX nur mit schriftlicher Erlaubnis von Raise.

**Robots-Fix (RFC 9309):** `urllib.robotparser` hatte zwei Schwächen und hat dadurch zu wenig gesperrt:
- Es kennt keine `*`/`$`-Wildcards, z. B. matchte `Disallow: /*?country=*` nie.
- Es nutzt nur die **erste** `User-agent: *`-Gruppe; CoinGate hat zwei.

Neu: `net/robots.py` (`RobotsRules`):
- führt Gruppen zusammen und matcht `*`/`$`;
- längste Regel gewinnt, bei Gleichstand gewinnt Allow;
- normalisiert Prozent-Encoding und unterstützt Crawl-delay;
- Tests in `tests/test_robots_rfc9309.py`.

`SafeHttpClient` nutzt den Matcher für alle Connectoren. `post_json` kann jetzt `Accept` setzen und erlaubt nur MCP-Protokoll-Header.

**Fehlerarten** (alle Connectoren dieser Gruppe):
- 429 ⇒ `RateLimited`
- 403 (inkl. Cloudflare) ⇒ `AccessDenied`
- 401/Login-Redirect ⇒ `AuthLost`
- robots-Sperre ⇒ `RobotsDisallowed`
- 404/5xx/JSON-RPC-Fehler/MCP-`isError` ⇒ `UpstreamError`
- fehlender Anker oder Schemaänderung ⇒ `ParserBroken`
- leere Liste ohne explizite 0-Meldung ⇒ `UnexpectedEmpty`

Jede gestörte Seite wird zu einer `:page`-Route mit Fehler (Scan `degraded`), nie zu „0 Angebote“.

**Evidence:** Parser-Version, Body- und Daten-Hash, der Lead, ob robots.txt geprüft wurde, `source_role = discovery_only`, `source_kind = aggregator` und `fetched_at_utc`.

**Fixtures:** `tests/fixtures/recorded/{coingate,buysellvouchers,cardbear,giftcardwiki}_2026-10-06/` (aufgenommen mit `scripts/record_fixtures.py <key>`). Gespeichert sind nur minimale Auszüge:
- BSV: Usernamen und User-IDs gehasht, nur öffentliche Store-Namen behalten;
- CoinGate: lange Texte entfernt, nie eine E-Mail gesendet;
- CardBear/GCW: nur die Tabelle.

**Jobs:** je ein täglicher Job (`*_aggregator_daily`, `interval_seconds = 86400`, `min_interval_seconds = 43200`). Er wirkt erst nach einem Worker-Neustart.

**Live-Smokes:** `docs/live_smoke_2026-10-06_{coingate,buysellvouchers,cardbear,giftcardwiki}.md`.

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

## 0c. TypeSafe (Enrichment-Layer, D-42) – Live-Doku geprüft 06.10.2026, 13:07–13:14 CEST

Quelle der API-Form (nichts erfunden; per WebFetch gelesen am 06.10.2026):
- https://docs.typesafe.ai/llms.txt (Index)
- https://docs.typesafe.ai/api.md – `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <API_KEY>`, Body `{state, model, questions}`, Antworten `{model, answers, usage}`; Fehler 401/422/429/529
- https://docs.typesafe.ai/sdk/python.md und https://docs.typesafe.ai/sdk/python/api/clients/sync.md – SDK `typesafe-sdk` (`TypeSafeClient.system_one`, Env `TYPESAFE_API_KEY`, httpx2-Transport); PyPI-Metadaten 0.7.2 vom 26.09.2026 (https://pypi.org/pypi/typesafe-sdk/json)
- https://docs.typesafe.ai/primitives.md, https://docs.typesafe.ai/primitives/choice.md, https://docs.typesafe.ai/primitives/noul.md, https://docs.typesafe.ai/primitives/score.md – Fragetypen, Limits (Choice ≤ 255 Optionen, Score 2–10 Stufen), Antwortfelder, „other/none“-Option, mehrere Fragen je Request
- https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md – Code behält die Kontrolle, atomare Fragen, Schwellen im Code
- https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook.md – Muster „Regex findet Kandidaten, Modell wählt, Code kopiert“ (Vorlage für `select_face_value`)
- https://docs.typesafe.ai/models.md – Modell `jev-1.13.0`, Alias `jev-latest` (Default), Rate-Limits 80 req/s, Input-Token-Preis

Live-Probe 06.10.2026 13:13 CEST (ohne Schlüssel, nichts Vertrauliches gesendet):
- `curl -X POST https://api.typesafe.ai/v1/systemone` ohne Key ⇒ **HTTP 403** `{"detail":{"error_type":"authentication_error","message":"Must supply an API key! ..."}}` (Doku nennt 401; beide werden als Auth-Fehler ⇒ abstain behandelt).
- **Box-Besonderheit:** Der Box-Resolver liefert für `api.typesafe.ai` (und `docs.typesafe.ai`) **198.18.0.1** (RFC-2544-Benchmark-Netz, Egress-Abfangung der Box). Der SSRF-Guard (D-26) lehnt nicht-öffentliche Adressen ab ⇒ der Provider antwortet auf **dieser Box** mit `blocked_url` ⇒ abstain. Der Guard wurde bewusst **nicht** aufgeweicht; Livebetrieb auf der Box braucht eine Nutzerentscheidung (siehe `docs/operations.md`).
- Nicht verifiziert (kein Schlüssel): eine erfolgreiche authentifizierte Antwort. Der Parser folgt exakt den Beispielantworten der Doku und lehnt alles Abweichende ab (⇒ abstain).

Daten, die gesendet würden: öffentliche Angebotsdaten (Titel, Händler, Region, Variante, Preistext, gekürzter Connector-Payload) und die Zielregion (`DE`). Keine Zugangsdaten, keine Nutzerdaten.

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
