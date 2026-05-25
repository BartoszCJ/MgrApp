# Ground Truth Data

Ten katalog zawiera "wzorcowa prawde" dla case studies wykorzystywanych w eksperymentach pracy magisterskiej. Kazdy plik JSON to publicznie udokumentowany hack z konkretnymi adresami atakujacych, adresami posrednimi i destynacjami srodkow.

## Po co to istnieje

Bez ground truth nie da sie mierzyc skutecznosci narzedzia forensics. Metryki precision/recall potrzebuja referencyjnej listy "tak/nie" - ktore adresy faktycznie sa zwiazane z hackiem, a ktore nie. Te pliki dostarczaja takiej listy zebranej z publicznie dostepnych raportow Chainalysis, Elliptic, Coinbase, Mandiant, TRM Labs i niezaleznych badaczy.

## Polityka jakosci

Wszystkie adresy w tym katalogu pochodza z **publicznie opublikowanych zrodel**, glownie:

- Raporty firm forensics: Chainalysis, Elliptic, TRM Labs, Mandiant
- Analizy giełd: Coinbase blog, Binance security
- Repozytoria badawcze open-source: tayvano/lazarus-bluenoroff-research
- Oficjalne komunikaty: US Treasury OFAC, FBI, US DoJ
- Niezalezni badacze: ZachXBT, SlowMist, Numen Cyber Labs

Kazdy plik ma sekcje `sources` z linkami. Adresy nie pochodzace z publicznych zrodel nie sa tu wpisywane.

## Pliki

- `ronin.json` - Ronin Bridge hack (2022-03-23, $625M, Lazarus Group/DPRK)
- `euler.json` - Euler Finance hack (2023-03-13, $197M, srodki zwrocone)
- `nomad.json` - Nomad Bridge hack (2022-08-01, $190M, free-for-all 88+ exploiterow)

## Schema (wspolne pola)

```jsonc
{
  "case": "Nazwa case study",
  "date": "YYYY-MM-DD - data ataku",
  "attack_block": 0,                   // pierwszy blok exploita na Ethereum
  "attribution": "Kto stoi za atakiem",
  "stolen_value_usd": 0,               // szacowana wartosc w USD w momencie hacku
  "stolen_assets": [                   // lista skradzionych tokenow
    {"asset": "ETH", "amount": 0}
  ],
  "summary": "Krotki opis ataku po polsku",
  "sources": ["lista URL"],            // publiczne raporty i analizy
  "addresses": {
    "attacker_root": [                 // glowne portfele atakujacego (root BFS)
      {"address": "0x...", "role": "...", "notes": "..."}
    ],
    "exploit_contracts": [             // smart contracty exploitu
      {"address": "0x...", "role": "...", "notes": "..."}
    ],
    "intermediaries_to_tornado": [],   // adresy posrednie przed Tornado
    "intermediaries_to_cex": [],       // adresy posrednie przed CEX
    "destinations_cex": [],            // konkretne adresy CEX deposit
    "destinations_tornado": [],        // adresy Tornado pools uzytych
    "return_transactions": []          // (Euler) adresy zwracajace srodki
  },
  "expected_heuristic_hits": {         // co nasze heurystyki POWINNY trafic
    "tornado_cash": {"expected": true, "notes": "..."},
    "cex": {"expected": true, "exchanges": [...]},
    "bridges": {"expected": true, "notes": "..."},
    "peel_chain": {"expected": false, "notes": "..."}
  },
  "ground_truth_metrics": {            // liczby do precision/recall
    "total_attacker_root_addresses": 0,
    "total_intermediary_addresses": 0,
    "total_cex_deposit_addresses": 0,
    "estimated_tornado_volume_usd": 0,
    "recovered_usd": 0
  }
}
```

## Jak to bedzie uzyte (planowane)

Modul `backend/src/forensics/metrics.py` (do napisania w nastepnej iteracji) bedzie:

1. Ladowal odpowiedni plik ground truth dla wybranego case study.
2. Po zakonczonym trace porownywal:
   - **Recall**: ile adresow z `addresses.*` znalazl BFS?
   - **Precision**: jaki procent alertow z heurystyk pokrywa sie z `expected_heuristic_hits`?
   - **Coverage**: jaki procent estymowanego wolumenu z `estimated_tornado_volume_usd` algorytm wykryl?
   - **Latency**: ile czasu zajal trace per hops level?
3. Zwracal `MetricsReport` per case do zakladki "Metrics" w UI.

## Ograniczenia tego dataset

- **Publiczne raporty nie sa wyczerpujace.** Lazarus uzyl ponad 12,000 adresow do prania Ronina - tu mamy tylko ~30 najwazniejszych. Recall liczony per ta liste jest **dolnym ograniczeniem** - realne moze byc lepsze.
- **Adresy moga byc nieaktualne.** CEX deposit addresses czasem sa rotowane.
- **FTX upadl** w listopadzie 2022, niektore adresy FTX moga byc puste lub zablokowane.
- **Atrybucja przypuszczalna.** Klastry Mandiant dla Nomada to estymaty, nie 100% pewnosci.
- **Nie pokrywamy off-chain** (KYC, raporty wewnetrzne giełd, analizy fiat off-ramps).

To wszystko jest OK dla pracy magisterskiej - waznejest spojne, transparentnie udokumentowane podejscie, nie "perfect ground truth".

## Aktualizacja

Gdy znajdziesz nowe publicznie udokumentowane adresy:

1. Dodaj do odpowiedniej sekcji w `<case>.json`.
2. Dodaj zrodlo do listy `sources`.
3. Zaktualizuj `ground_truth_metrics.total_*` jesli dodajesz nowe adresy do klasycznych kategorii.
4. Dopisz wpis w `wiki/log.md` co dodano i z jakich zrodel.
