"""Klient Etherscan API.

Co to robi:
- pobiera transakcje danego adresu Ethereum,
- konwertuje surowe dane Etherscan do naszych modeli pydantic,
- bazowy klient na ktorym oprzemy graf.

Dokumentacja Etherscan: https://docs.etherscan.io/
"""

from datetime import datetime, timezone
from decimal import Decimal

import httpx
from loguru import logger

from forensics.config import settings
from forensics.core.models import Transaction

ETHERSCAN_BASE_URL = "https://api.etherscan.io/api"
WEI_PER_ETH = Decimal(10**18)


class EtherscanError(Exception):
    """Etherscan API zwrocil blad."""


class EtherscanClient:
    """Cienki klient nad Etherscan API."""

    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or settings.etherscan_api_key
        if not self.api_key:
            logger.warning("Brak ETHERSCAN_API_KEY - bedzie dzialac z rate limitem 1 req / 5s")
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self.client.aclose()

    async def get_normal_transactions(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99_999_999,
        page: int = 1,
        offset: int = 50,
        sort: str = "desc",
    ) -> list[Transaction]:
        """Pobiera 'normalne' transakcje adresu (bez internal i token transfers).

        Args:
            address: adres Ethereum (0x...).
            start_block / end_block: zakres blokow.
            page / offset: paginacja (offset = ile na strone, max 10000).
            sort: 'asc' lub 'desc' wg blockNumber.
        """
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
            "apikey": self.api_key,
        }

        logger.info("Etherscan txlist for {} (page={}, offset={})", address, page, offset)
        response = await self.client.get(ETHERSCAN_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        # Etherscan: status="1" = OK, status="0" = blad lub pusta lista
        if data.get("status") != "1":
            message = data.get("message", "")
            if "No transactions found" in message:
                return []
            raise EtherscanError(f"Etherscan: {message} ({data.get('result')})")

        raw_txs = data.get("result", [])
        return [self._parse_transaction(raw) for raw in raw_txs]

    @staticmethod
    def _parse_transaction(raw: dict) -> Transaction:
        """Konwersja surowego dict z Etherscan do naszego modelu."""
        value_wei = Decimal(raw.get("value", "0"))
        value_eth = float(value_wei / WEI_PER_ETH)
        return Transaction(
            hash=raw["hash"],
            block_number=int(raw["blockNumber"]),
            timestamp=datetime.fromtimestamp(int(raw["timeStamp"]), tz=timezone.utc),
            from_address=raw["from"].lower(),
            to_address=(raw.get("to") or "").lower() or None,
            value_wei=str(value_wei),
            value_eth=value_eth,
            gas_used=int(raw.get("gasUsed", 0)),
            is_error=raw.get("isError") == "1",
        )
