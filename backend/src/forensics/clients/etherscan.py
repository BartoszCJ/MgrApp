

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypeAlias

import httpx
from loguru import logger

from forensics import cache
from forensics.config import settings
from forensics.core.models import Transaction

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
ETHEREUM_MAINNET_CHAIN_ID = 1
WEI_PER_ETH = Decimal(10**18)
QueryParamValue: TypeAlias = str | int | float | bool | None


class EtherscanError(Exception):
    """Etherscan API zwrocil blad."""


class EtherscanClient:
    """Cienki klient nad Etherscan API V2."""

    def __init__(
        self,
        api_key: str | None = None,
        chain_id: int = ETHEREUM_MAINNET_CHAIN_ID,
        timeout: float = 10.0,
        min_interval: float = 0.4,
        max_retries: int = 3,
    ):
        self.api_key = api_key or settings.etherscan_api_key
        self.chain_id = chain_id
        if not self.api_key:
            logger.warning("Brak ETHERSCAN_API_KEY - bedzie dzialac z rate limitem 1 req / 5s")
        self.client = httpx.AsyncClient(timeout=timeout)
        # Rate limiting: free tier ~3-5 req/s. Serializujemy zapytania z odstepem
        # min_interval, zeby BFS nie wywalal "Max calls per sec rate limit reached".
        self._rate_lock = asyncio.Lock()
        self._last_request = 0.0
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._retry_delay = 1.0

    async def close(self) -> None:
        await self.client.aclose()

    async def check_connection(self) -> bool:
        """Lekki startup check: czy Etherscan odpowiada i czy klucz wyglada poprawnie."""
        params: dict[str, QueryParamValue] = {
            "chainid": self.chain_id,
            "module": "account",
            "action": "balance",
            "address": "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
            "tag": "latest",
            "apikey": self.api_key,
        }

        logger.opt(colors=True).info(
            "API check | Etherscan | <cyan>Call do API</cyan>: account.balance"
        )
        try:
            response = await self.client.get(ETHERSCAN_BASE_URL, params=params)
        except httpx.RequestError as exc:
            logger.opt(colors=True).warning(
                "API check | Etherscan | <red>Blad requestu</red>: {}", exc
            )
            return False

        if response.status_code < 400:
            logger.opt(colors=True).info(
                "API check | Etherscan | <cyan>Odpowiedz HTTP</cyan>: <green>{} {}</green>",
                response.status_code,
                response.reason_phrase,
            )
        else:
            logger.opt(colors=True).info(
                "API check | Etherscan | <cyan>Odpowiedz HTTP</cyan>: <red>{} {}</red>",
                response.status_code,
                response.reason_phrase,
            )
        if response.status_code >= 400:
            logger.opt(colors=True).warning(
                "API check | Etherscan | <red>API nie jest OK</red>: {}",
                response.text[:200],
            )
            return False

        try:
            data = response.json()
        except ValueError:
            logger.opt(colors=True).warning(
                "API check | Etherscan | <red>API nie jest OK</red>: response to nie JSON"
            )
            return False

        if data.get("status") == "1":
            logger.opt(colors=True).info("API check | Etherscan | <green>API jest OK</green>")
            return True

        message = data.get("message", "UNKNOWN")
        result = data.get("result", "")
        logger.opt(colors=True).warning(
            "API check | Etherscan | <red>API nie jest OK</red>: {} ({})", message, result
        )
        return False

    async def _cached_get(self, action: str, params: dict[str, QueryParamValue]) -> dict:
        """GET z dyskowym cache.

        Cache'uje TYLKO definitywne odpowiedzi (HTTP 200 i status='1' albo
        'No transactions found'). Bledy/transienty nie sa cache'owane.
        Klucz cache nie zawiera apikey - cache.read/write sanityzuja params.
        """
        env = cache.read("etherscan", action, dict(params))
        if env is not None:
            return env["payload"]

        data, status_code = await self._throttled_request(params)

        status_ok = data.get("status") == "1"
        no_tx = "No transactions found" in str(data.get("message", ""))
        if status_ok or no_tx:
            cache.write("etherscan", action, dict(params), data, status_code)
        return data

    async def _throttled_request(self, params: dict[str, QueryParamValue]) -> tuple[dict, int]:
        """GET z odstepem min_interval miedzy zapytaniami + retry na rate limit.

        Etherscan zglasza rate limit jako HTTP 200 ze statusem '0' i komunikatem
        'Max calls per sec rate limit reached' - dlatego retry patrzy na tresc, nie na HTTP.
        Lock serializuje zapytania, wiec rownolegly BFS nie przekracza limitu.
        """
        data: dict = {}
        status_code = 0
        for attempt in range(self._max_retries + 1):
            async with self._rate_lock:
                wait = self._min_interval - (time.monotonic() - self._last_request)
                if wait > 0:
                    await asyncio.sleep(wait)
                response = await self.client.get(ETHERSCAN_BASE_URL, params=params)
                self._last_request = time.monotonic()

            response.raise_for_status()
            status_code = response.status_code
            data = response.json()

            blob = f"{data.get('message', '')} {data.get('result', '')}".lower()
            if "rate limit" in blob and attempt < self._max_retries:
                await asyncio.sleep(self._retry_delay * (attempt + 1))
                continue
            return data, status_code
        return data, status_code

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
        params: dict[str, QueryParamValue] = {
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
        data = await self._cached_get("txlist", params)

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
        params: dict[str, QueryParamValue] = {
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
        data = await self._cached_get("tokentx", params)

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
            timestamp=datetime.fromtimestamp(int(raw["timeStamp"]), tz=UTC),
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
            timestamp=datetime.fromtimestamp(int(raw["timeStamp"]), tz=UTC),
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
