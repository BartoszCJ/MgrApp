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
    """Pojedyncza transakcja Ethereum."""

    hash: str = Field(description="Hash transakcji")
    block_number: int = Field(description="Numer bloku")
    timestamp: datetime = Field(description="Czas wykonania")
    from_address: str = Field(description="Adres nadawcy")
    to_address: str | None = Field(default=None, description="Adres odbiorcy (None dla creation)")
    value_wei: str = Field(description="Wartosc w wei (string bo moze byc > 2^53)")
    value_eth: float = Field(description="Wartosc w ETH dla wygody")
    gas_used: int = Field(description="Zuzyty gas")
    is_error: bool = Field(default=False, description="Czy transakcja sie nie powiodla")


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
    max_depth: int = Field(default=2, ge=1, le=5, description="Glebokosc grafu")
    max_transactions: int = Field(default=50, ge=1, le=500)


class TraceResult(BaseModel):
    """Wynik sledzenia: graf transakcji + etykiety."""

    root_address: str
    transactions: list[Transaction]
    labels: list[AddressLabel] = Field(default_factory=list)
    total_transactions: int = 0
    notes: list[str] = Field(default_factory=list)
