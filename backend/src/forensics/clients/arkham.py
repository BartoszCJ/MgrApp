"""Klient Arkham Intelligence API.

Co to robi:
- pyta Arkham o etykiete dla danego adresu (kto to jest),
- zwraca strukture `AddressLabel` (entity, label, category, source),
- batch lookup wielu adresow rownolegle (asyncio.gather z limitem rate).

Dokumentacja: https://codex.arkm.com/arkham-api
Endpoint adresu: GET https://api.arkm.com/intelligence/address/{address}/all
Auth: header `API-Key: <key>`.
Rate limit basic tier: ~20 req/s.

UWAGA: format response Arkhama nie jest super dobrze udokumentowany publicznie.
Klient stara sie wyciagnac to co najwazniejsze (entity name, type) i ignorowac reszte.
Jesli adres jest nieznany, Arkham moze zwrocic 404, 200 z pustym body,
albo strukture bez `arkhamEntity`.
"""

import asyncio
from typing import Any

import httpx
from loguru import logger

from forensics.config import settings
from forensics.core.models import AddressLabel

ARKHAM_BASE_URL = "https://api.arkm.com"
DEFAULT_CONCURRENCY = 8  # liczba rownoleglych zapytan, ponizej rate limita 20/s


class ArkhamError(Exception):
    """Arkham API zwrocil blad."""


class ArkhamClient:
    """Cienki klient nad Arkham Intelligence API."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 10.0,
        concurrency: int = DEFAULT_CONCURRENCY,
    ):
        self.api_key = api_key or settings.arkham_api_key
        if not self.api_key:
            logger.warning("Brak ARKHAM_API_KEY - klient nie bedzie zwracal etykiet")
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={"API-Key": self.api_key} if self.api_key else {},
        )
        self._semaphore = asyncio.Semaphore(concurrency)

    async def close(self) -> None:
        await self.client.aclose()

    async def get_address_intelligence(self, address: str) -> AddressLabel | None:
        """Pyta Arkham o pojedynczy adres.

        Returns:
            AddressLabel jesli Arkham cos wie o tym adresie,
            None jesli adres jest nieznany lub brak klucza API.
        """
        if not self.api_key:
            return None

        url = f"{ARKHAM_BASE_URL}/intelligence/address/{address}/all"

        async with self._semaphore:
            try:
                response = await self.client.get(url)
            except httpx.RequestError as exc:
                logger.warning("Arkham request error for {}: {}", address, exc)
                return None

        if response.status_code == 404:
            return None
        if response.status_code == 401:
            raise ArkhamError("Arkham 401 Unauthorized - sprawdz ARKHAM_API_KEY w .env")
        if response.status_code == 429:
            logger.warning("Arkham 429 rate limit hit for {}", address)
            return None
        if response.status_code >= 400:
            logger.warning(
                "Arkham {} for {}: {}", response.status_code, address, response.text[:200]
            )
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        if not data:
            return None

        return self._parse_address(address, data)

    async def get_many(self, addresses: list[str]) -> dict[str, AddressLabel]:
        """Batch lookup. Zwraca slownik adres -> AddressLabel (tylko dla znanych)."""
        if not addresses:
            return {}

        unique = list({addr.lower() for addr in addresses})
        logger.info("Arkham batch lookup: {} unique addresses", len(unique))

        tasks = [self.get_address_intelligence(addr) for addr in unique]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: dict[str, AddressLabel] = {}
        for addr, result in zip(unique, results, strict=False):
            if isinstance(result, AddressLabel):
                out[addr] = result
            elif isinstance(result, Exception):
                logger.warning("Arkham failed for {}: {}", addr, result)
        return out

    @staticmethod
    def _parse_address(address: str, data: dict[str, Any]) -> AddressLabel | None:
        """Wyciaga to co istotne z response Arkhama.

        Response Arkhama bywa per-chain (np. `ethereum`, `bitcoin`) lub flat.
        Probujemy obu wariantow.
        """
        # Wariant 1: flat na top-level
        entity = data.get("arkhamEntity") or {}
        label_data = data.get("arkhamLabel") or {}

        # Wariant 2: response per-chain (np. dla multichain entity)
        # bierzemy pierwsze niepuste
        if not entity and not label_data:
            for chain_data in data.values():
                if isinstance(chain_data, dict):
                    chain_entity = chain_data.get("arkhamEntity")
                    chain_label = chain_data.get("arkhamLabel")
                    if chain_entity or chain_label:
                        entity = chain_entity or {}
                        label_data = chain_label or {}
                        break

        entity_name = entity.get("name")
        label_name = label_data.get("name")
        entity_type = entity.get("type")  # np. "cex", "individual", "fund", "mixer"

        # nic ciekawego - adres nieznany
        if not entity_name and not label_name:
            return None

        # category mapping - probujemy zgadnac kategorie z type/name
        category = ArkhamClient._guess_category(entity_type, entity_name, label_name)

        return AddressLabel(
            address=address.lower(),
            label=label_name or entity_name,
            entity=entity_name,
            category=category,
            source="arkham",
        )

    @staticmethod
    def _guess_category(
        entity_type: str | None,
        entity_name: str | None,
        label_name: str | None,
    ) -> str | None:
        """Mapuje typ/nazwe z Arkhama na nasza prosta kategorie do kolorowania badge'ow.

        Priorytety (od najwyzszego):
          1. hacker - wszystko co wskazuje na atak/sankcje (OFAC, exploit, drainer, scam, Lazarus).
             Ma priorytet nad bridge/cex/mixer bo "Ronin Bridge Exploiter" to hacker, nie bridge.
          2. mixer - Tornado Cash, Wasabi, Samourai itp.
          3. bridge - Wormhole, Multichain, Synapse itp.
          4. cex - giełdy scentralizowane.
          5. fallback: entity_type z Arkhama jak nie ma trafien.
        """
        candidates = " ".join(filter(None, [entity_type, entity_name, label_name])).lower()

        hacker_kw = (
            "exploiter",
            "exploit",
            "hacker",
            "drainer",
            "scam",
            "lazarus",
            "ofac",
            "sanction",
            "north korea",
        )
        if any(k in candidates for k in hacker_kw):
            return "hacker"
        if any(k in candidates for k in ("mixer", "tornado", "wasabi", "samourai")):
            return "mixer"
        bridge_kw = ("bridge", "wormhole", "multichain", "synapse", "stargate")
        if any(k in candidates for k in bridge_kw):
            return "bridge"
        cex_kw = (
            "cex",
            "exchange",
            "binance",
            "coinbase",
            "kraken",
            "okx",
            "bybit",
            "kucoin",
            "hot wallet",
        )
        if any(
            k in candidates
            for k in cex_kw
        ):
            return "cex"
        if entity_type:
            return entity_type
        return None
