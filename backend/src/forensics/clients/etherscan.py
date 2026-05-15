"""Klient Etherscan API V2 (multichain).

Co to robi:
- pobiera transakcje danego adresu Ethereum,
- konwertuje surowe dane Etherscan do naszych modeli pydantic,
- bazowy klient na ktorym oprzemy graf.

Dokumentacja Etherscan V2: https://docs.etherscan.io/etherscan-v2
V1 -> V2: https://docs.etherscan.io/v2-migration

Roznica V1 vs V2:
- V1 URL: https://api.etherscan.io/api
- V2 URL: https://api.etherscan.io/v2/api z parametrem chainid
- chainid=1 dla Ethereum mainnet, 56 dla BSC, 137 dla Polygon, 42161 dla Arbitrum itd.
- V1 zostal deprecated 31 maja 2025.
"""

from datetime import datetime, timezone
from decimal import Decimal

import httpx
from loguru import logger

from forensics.config import settings
from forensics.core.models import Transaction

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
ETHEREUM_MAINNET_CHAIN_ID = 1
WEI_PER_ETH = Decimal(10**18)


class EtherscanError(Exception):
    """Etherscan API zwrocil blad."""


class EtherscanClient:
    """Cienki klient nad Etherscan API V2."""

    def __init__(
        self,
        api_key: str | None = None,
        chain_id: int = ETHEREUM_MAINNET_CHAIN_ID,
        timeout: float = 10.0,
    ):
        self.api_key = api_key or settings.etherscan_api_key
        self.chain_id = chain_id
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
            "chainid": self.chain_id,
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

        logger.info(
            "Etherscan V2 txlist for {} (chain={}, page={}, offset={})",
            address,
            self.chain_id,
            page,
            offset,
        )
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

    async def get_token_transfers(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99_999_999,
        page: int = 1,
        offset: int = 50,
        sort: str = "desc",
    ) -> list[Transaction]:
        """Pobiera transfery tokenow ERC-20 dla adresu.

        Wazne bo wiekszosc ruchu z hackow to tokeny (USDC, USDT, WETH), nie czyste ETH.
        Dla hackera Ronin Bridge `txlist` pokazuje glownie 0.0000 ETH wywolan contractowych,
        a prawdziwy ruch (~$625M) byl w USDC/WETH - widoczny tylko przez `tokentx`.
        """
        params = {
            "chainid": self.chain_id,
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
            "apikey": self.api_key,
        }

        logger.info(
            "Etherscan V2 tokentx for {} (chain={}, page={}, offset={})",
            address,
            self.chain_id,
            page,
            offset,
        )
        response = await self.client.get(ETHERSCAN_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "1":
            message = data.get("message", "")
            if "No transactions found" in message:
                return []
            raise EtherscanError(f"Etherscan tokentx: {message} ({data.get('result')})")

        raw_txs = data.get("result", [])
        return [self._parse_token_transfer(raw) for raw in raw_txs]

    @staticmethod
    def _parse_transaction(raw: dict) -> Transaction:
        """Konwersja surowego dict z Etherscan (normalna tx) do naszego modelu."""
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

    @staticmethod
    def _parse_token_transfer(raw: dict) -> Transaction:
        """Konwersja transferu tokenu ERC-20 do naszego modelu.

        Roznica vs normalna tx:
        - value jest w jednostkach tokenu (nie wei),
        - decimals trzeba uwzglednic przy konwersji do floata,
        - dodajemy token_symbol/name/contract/decimals.
        """
        decimals = int(raw.get("tokenDecimal", 18) or 18)
        raw_value = Decimal(raw.get("value", "0"))
        divisor = Decimal(10) ** decimals
        value_normalized = float(raw_value / divisor)

        return Transaction(
            hash=raw["hash"],
            block_number=int(raw["blockNumber"]),
            timestamp=datetime.fromtimestamp(int(raw["timeStamp"]), tz=timezone.utc),
            from_address=raw["from"].lower(),
            to_address=(raw.get("to") or "").lower() or None,
            value_wei=str(raw_value),
            value_eth=value_normalized,  # tu trzymamy wartosc w jednostkach tokenu
            gas_used=int(raw.get("gasUsed", 0)),
            is_error=False,
            token_symbol=raw.get("tokenSymbol"),
            token_name=raw.get("tokenName"),
            token_contract=raw.get("contractAddress", "").lower() or None,
            token_decimals=decimals,
        )
