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


class TraceResult(BaseModel):
    """Wynik sledzenia: graf transakcji + etykiety + alerty z heurystyk."""

    root_address: str
    transactions: list[Transaction]
    labels: list[AddressLabel] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    graph: TraceGraph | None = Field(default=None, description="Graf BFS przeplywu (jesli hops > 1)")
    total_transactions: int = 0
    notes: list[str] = Field(default_factory=list)
