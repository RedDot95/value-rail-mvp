# Einzige Marktquelle

https://coingate.com/gift-cards/clearance

Der Connector liest die verlinkte Seite und die öffentliche, von ihr verwendete Suchkonfiguration. Er fragt ausschließlich deren Clearance-Inventar mit `provider:resale AND resale_listable:true` ab. Statische Browser-Dateien und die Such-API sind Hilfsendpunkte derselben Seite; andere Händler, normale CoinGate-Angebote und Wechselkursdienste werden nicht abgefragt. Keine eigenen API-Zugangsdaten erforderlich.

Pagination wird vollständig geprüft. Bei unvollständigen Listen werden Angebote nicht als verschwunden markiert. Nicht verfügbare, reservierte oder abgelaufene Codes werden ausgelassen. Spiele und Streaming werden über den Instrumentenkatalog ausgeschlossen; Länderbeschränkungen werden angezeigt, nicht automatisch auf Deutschland eingeschränkt.

Berechnung: `1 − Kaufpreis / Nennwert`, in derselben Währung. Der veröffentlichte CoinGate-Rabatt gegenüber dem regulären Verkaufspreis kann davon abweichen. Gebühren und Auszahlungswege bleiben unbewertet.

Identische Marke, Nennwert, Währung, Länder und Ablaufdatum werden gruppiert: günstigster beobachteter Preis und Anzahl der Codes zu diesem Preis. Neue Treffer, materielle Preisänderungen und wieder aufgefüllter Bestand können Pushs auslösen. Verkaufte oder abgelaufene Angebote werden vor dem Versand unterdrückt.
