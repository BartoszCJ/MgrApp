# Forensics Blockchain Tracer

Prototyp systemu wspomagającego analizę aktywności transakcyjnej w sieci Ethereum po incydentach bezpieczeństwa. Projekt powstał w ramach pracy magisterskiej.

## Funkcje

- pobieranie transakcji natywnych ETH i transferów ERC-20 z Etherscan API,
- normalizacja danych pochodzących z różnych operacji API,
- budowa skierowanego grafu relacji transakcyjnych z użyciem BFS,
- eksploracja obejmująca od jednego do trzech przejść między adresami,
- opcjonalne etykietowanie adresów za pomocą Arkham API,
- wykrywanie kontaktu ze znanymi adresami Tornado Cash, mostów międzyłańcuchowych i giełd scentralizowanych,
- wykrywanie kandydatów wzorca `peel chain`,
- prezentacja grafu, alertów, transakcji, etykiet i metryk w aplikacji webowej,
- dyskowa pamięć podręczna odpowiedzi zewnętrznych usług,
- przeprowadzanie eksperymentów dla przypadków Ronin Bridge, Euler Finance i Nomad Bridge,
- eksport podsumowań eksperymentów do formatów JSON, Markdown i CSV.

## Technologie

Warstwa serwerowa:

- Python 3.11 lub nowszy,
- FastAPI,
- Uvicorn,
- HTTPX,
- Pydantic,
- pytest.

Warstwa kliencka:

- Next.js 16,
- React 19,
- TypeScript,
- React Flow,
- Tailwind CSS 4.

## Wymagania

- Python 3.11 lub nowszy,
- Node.js 20.9 lub nowszy,
- npm,
- [uv](https://docs.astral.sh/uv/),
- klucz Etherscan API do pobierania danych na żywo,
- opcjonalnie klucz Arkham API do etykietowania adresów.

## Konfiguracja

Utwórz plik `backend/.env`:

```env
ETHERSCAN_API_KEY=twoj_klucz_etherscan
ARKHAM_API_KEY=opcjonalny_klucz_arkham
FRONTEND_URL=http://localhost:3000
```

Klucz Arkham nie jest wymagany do budowy grafu ani wykonywania heurystyk. Bez niego aplikacja nie pobierze zewnętrznych etykiet adresów.

Frontend domyślnie łączy się z backendem pod adresem `http://localhost:8000`. W razie potrzeby można utworzyć plik `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Jeżeli frontend zostanie uruchomiony na porcie innym niż `3000`, wartość `FRONTEND_URL` musi wskazywać jego rzeczywisty adres.

## Instalacja

W katalogu głównym repozytorium wykonaj:

```powershell
npm run install:all
```

Polecenie instaluje zależności głównego projektu, backendu i frontendu.

## Uruchomienie

Backend i frontend można uruchomić wspólnie:

```powershell
npm run dev
```

Po uruchomieniu:

- aplikacja webowa: `http://localhost:3000`,
- backend API: `http://127.0.0.1:8000`,
- dokumentacja OpenAPI: `http://127.0.0.1:8000/docs`.

Usługi można również uruchamiać oddzielnie:

```powershell
npm run dev:backend
npm run dev:frontend
```

## Weryfikacja techniczna

Testy backendu:

```powershell
npm run test:backend
```

Kontrola jakości kodu backendu:

```powershell
npm run lint:backend
uv --project backend run --extra dev mypy backend/src
```

Test i kontrola typów frontendu:

```powershell
npm --prefix frontend run test:format
npm --prefix frontend run type-check
```

Kompilacja wersji produkcyjnej frontendu:

```powershell
npm run build:frontend
```

## Operacje API

| Metoda | Ścieżka | Przeznaczenie |
|---|---|---|
| `GET` | `/` | sprawdzenie dostępności backendu |
| `POST` | `/api/trace` | uruchomienie analizy wskazanego adresu |
| `GET` | `/api/cache/status` | odczyt stanu pamięci podręcznej |
| `DELETE` | `/api/cache` | usunięcie zapisanych odpowiedzi |
| `POST` | `/api/experiments` | zapis podsumowania eksperymentu |

Szczegółowy opis modeli żądań i odpowiedzi jest dostępny w dokumentacji OpenAPI.

## Struktura projektu

```text
MgrApp/
├── backend/
│   ├── data/
│   │   ├── ground_truth/
│   │   └── known_addresses/
│   ├── src/forensics/
│   └── tests/
├── frontend/
│   └── src/
├── results/
│   └── experiments/
├── package.json
└── README.md
```

## Wyniki eksperymentów

Katalog `results/experiments` zawiera wybrane podsumowania badań dla głębokości dwóch i trzech przejść. Każde wykonanie jest zapisane w formatach JSON, Markdown i CSV.

Pliki zawierają parametry wykonania, skrót zatwierdzenia Git, wartości metryk, rozmiar grafu, liczbę alertów oraz statystyki pamięci podręcznej. Nie zawierają pełnego grafu ani pełnej historii transakcji.

Pamięć podręczna odpowiedzi zewnętrznych usług (`backend/.cache`) nie jest częścią repozytorium. Uruchomienie analizy po sklonowaniu projektu wymaga zatem ważnego klucza Etherscan API i pobrania danych na nowo. Czas pierwszego wykonania jest wtedy znacznie dłuższy niż przy korzystaniu z zapisanych wcześniej odpowiedzi.

## Ograniczenia

- prototyp analizuje wyłącznie główną sieć Ethereum,
- pobierane są transakcje natywne ETH oraz transfery ERC-20; wywołania wewnętrzne nie są uwzględniane,
- liczba rekordów pobieranych dla każdego adresu jest ograniczona,
- graf przedstawia sąsiedztwo transakcyjne i nie potwierdza przepływu tych samych jednostek aktywów,
- eksploracja nie wymusza chronologicznego następstwa kolejnych relacji,
- listy znanych adresów i zbiory referencyjne zostały przygotowane ręcznie i mogą być niepełne,
- etykiety Arkham mają charakter pomocniczy i nie stanowią dowodu tożsamości podmiotu,
- mechanizm pamięci podręcznej ułatwia powtarzanie analiz, ale nie gwarantuje pełnej odtwarzalności danych,
- rozwiązanie ma charakter badawczego prototypu wspomagającego analizę i nie zastępuje pełnego postępowania dochodzeniowego.
