"""Pydantic modele danych uzywane w calym backendzie.

Co to robi:
- definiuje "ksztalt" obiektow (Transaction, Address, TraceResult),
- automatycznie waliduje dane przychodzace z API,
- serializuje/deserializuje JSON <-> Python,
- te modele sa zwracane w endpointach FastAPI i tworza Swagger UI.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """Pojedyncza transakcja Ethereum (normalna lub token transfer)."""

    hash: str = Field(description="Hash transakcji")
    block_number: int = Field(description="Numer bloku")
    timestamp: datetime = Field(description="Czas wykonania")
    from_address: str = Field(description="Adres nadawcy")
    to_address: str | None = Field(default=None, description="Adres odbiorcy (None dla creation)")
    value_wei: str = Field(
        description="Wartosc w wei/jednostkach tokenu (string bo moze byc > 2^53)"
    )
    value_eth: float = Field(description="Wartosc w ETH lub tokenie dla wygody")
    gas_used: int = Field(default=0, description="Zuzyty gas (0 dla token transferow)")
    is_error: bool = Field(default=False, description="Czy transakcja sie nie powiodla")
    # Token transfer specific (None dla normalnych ETH transakcji)
    token_symbol: str | None = Field(default=None, description="Symbol tokenu np. USDC, WETH")
    token_name: str | None = Field(default=None, description="Pelna nazwa tokenu")
    token_contract: str | None = Field(default=None, description="Adres kontraktu tokenu")
    token_decimals: int | None = Field(
        default=None,
        description="Liczba miejsc po przecinku tokenu",
    )


class AddressLabel(BaseModel):
    """Etykieta adresu z Arkham / lokalnej bazy."""

    address: str
    label: str | None = Field(default=None, description="np. 'Binance Hot Wallet 7'")
    entity: str | None = Field(default=None, description="np. 'Binance', 'Tornado Cash'")
    category: str | None = Field(default=None, description="np. 'cex', 'mixer', 'bridge', 'hacker'")
    source: str | None = Field(default=None, description="np. 'arkham', 'manual'")


class TraceRequest(BaseModel):
    """Wejscie do endpointu /api/trace."""

    address: str = Field(description="Adres startowy do sledzenia")
    hops: int = Field(default=2, ge=1, le=3, description="Glebokosc grafu BFS (1-3)")
    max_transactions: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Max tx pobranych dla roota (hop 0)",
    )
    max_per_hop: int = Field(
        default=20,
        ge=5,
        le=50,
        description="Max tx pobranych per node dla hop >= 1 (mniejsze, zeby nie zalac API)",
    )
    start_block: int | None = Field(
        default=None,
        ge=0,
        description="Okno incydentu: dolny blok (None = od poczatku lancucha).",
    )
    end_block: int | None = Field(
        default=None,
        ge=0,
        description="Okno incydentu: gorny blok (None = do najnowszego).",
    )
    case_name: str | None = Field(
        default=None,
        description=(
            "Nazwa case study do ewaluacji metryk (np. 'ronin', 'euler', 'nomad'). "
            "Musi istniec plik data/ground_truth/<case_name>.json. None = bez metryk."
        ),
    )


class Alert(BaseModel):
    """Znalezisko z heurystyki - cos co warto pokazac analitykowi.

    Severity:
      - info: neutralna obserwacja (np. "duza koncentracja transferow w 1 bloku")
      - warning: cos podejrzanego ale nie pewnego (np. "adres mial kontakt z bridge")
      - critical: pewny problem (np. "deposit do Tornado Cash - srodki zostaja ukryte")
    """

    type: str = Field(description="np. 'tornado_cash_deposit', 'tornado_cash_withdraw'")
    severity: str = Field(description="info | warning | critical")
    title: str = Field(description="Krotki tytul, np. 'Deposit do Tornado Cash 100 ETH'")
    message: str = Field(description="Pelniejsze wyjasnienie")
    related_addresses: list[str] = Field(default_factory=list)
    related_tx_hashes: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class GraphNode(BaseModel):
    """Wezel grafu BFS: adres + metadata.

    `depth` to liczba hopow od roota (0 = root, 1 = bezposredni kontrahent itd).
    `is_endpoint` = True dla znanych terminali (mixer/CEX/bridge) - nie ekspandujemy ich dalej.
    """

    address: str
    depth: int
    tx_count: int = 0  # ile transakcji adresu zostalo wziete do grafu
    is_endpoint: bool = False
    is_root: bool = False


class GraphEdge(BaseModel):
    """Krawedz grafu = pojedyncza transakcja miedzy dwoma adresami."""

    source: str = Field(description="Adres nadawcy (from)")
    target: str = Field(description="Adres odbiorcy (to)")
    tx_hash: str
    value: float = Field(description="Wartosc w ETH lub w jednostkach tokenu")
    token: str | None = Field(default=None, description="Symbol tokenu lub None dla ETH")
    block: int


class TraceGraph(BaseModel):
    """Pelny graf BFS: wezly + krawedzie + metadata."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    root_address: str
    hops: int
    fetched_addresses: int = Field(
        default=0,
        description="Ile adresow zostalo zapytanych w Etherscan",
    )


class MetricsReport(BaseModel):
    """Raport metryk efektywnosci dla pojedynczego trace vs ground truth.

    Wszystkie procenty w skali 0.0-1.0. Pole `breakdown` zawiera surowe liczby
    (znalezione/oczekiwane) zeby UI mogl pokazac "12/15 adresow".

    Mapowanie heurystyk -> typy alertow:
      - tornado_cash -> tornado_cash_deposit, tornado_cash_withdraw
      - cex -> cex_outgoing, cex_incoming
      - bridges -> bridge_outgoing, bridge_incoming
      - peel_chain -> peel_chain
    """

    case_name: str = Field(description="Nazwa case study, np. 'ronin'")

    address_recall: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Ile znanych adresow z ground truth znalazl BFS, w przedziale 0-1. "
            "Liczone jako |found ∩ expected| / |expected|."
        ),
    )
    heuristic_precision: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Ile typow heurystyk ktore zgłosily trafienie mialo do tego prawo wg ground truth."
            " 1.0 = brak fałszywych alarmow. Liczone na poziomie kategorii"
            " (tornado/cex/bridge/peel)."
        ),
    )
    heuristic_recall: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Ile oczekiwanych heurystyk (expected=True w ground truth) zostalo trafionych. "
            "Liczone na poziomie kategorii."
        ),
    )
    cex_coverage: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Procent oczekiwanych gield (z ground_truth.expected_heuristic_hits.cex.exchanges) "
            "ktore pojawily sie w alertach. 1.0 jesli wszystkie znalezione."
        ),
    )

    latency_seconds: float = Field(
        ge=0.0,
        description="Czas wykonania calego trace endpoint (BFS + Arkham + heurystyki + metryki).",
    )

    breakdown: dict = Field(
        default_factory=dict,
        description=(
            "Surowe liczby: addresses_found, addresses_expected, heuristics_hit, "
            "heuristics_expected, cex_exchanges_found, cex_exchanges_expected itp."
        ),
    )

    notes: list[str] = Field(
        default_factory=list,
        description="Uwagi: nieoczekiwane alerty, brak danych, hint na false positive.",
    )


class TraceResult(BaseModel):
    """Wynik sledzenia: graf transakcji + etykiety + alerty z heurystyk."""

    root_address: str
    transactions: list[Transaction]
    labels: list[AddressLabel] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    graph: TraceGraph | None = Field(
        default=None,
        description="Graf BFS przeplywu (jesli hops > 1)",
    )
    total_transactions: int = 0
    notes: list[str] = Field(default_factory=list)
    metrics: MetricsReport | None = Field(
        default=None,
        description="Metryki efektywnosci jesli case_name byl podany w requescie.",
    )
