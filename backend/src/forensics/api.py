"""FastAPI app — REST API dla frontendu.

Co to robi:
- wystawia endpointy HTTP do ktorych gada frontend,
- konfiguruje CORS zeby Next.js mogl wolac z innego portu,
- dokumentacja automatycznie pod /docs (Swagger UI).
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from forensics import __version__
from forensics.clients.arkham import ArkhamClient, ArkhamError
from forensics.clients.etherscan import EtherscanClient, EtherscanError
from forensics.config import settings
from forensics.core.models import TraceRequest, TraceResult
from forensics.heuristics.known_address import detect_known_group
from forensics.heuristics.tornado import detect_tornado


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Setup i cleanup zasobow przy starcie/zakonczeniu serwera."""
    logger.info("Forensics API starting (v{})", __version__)
    app.state.etherscan = EtherscanClient()
    app.state.arkham = ArkhamClient()
    yield
    await app.state.etherscan.close()
    await app.state.arkham.close()
    logger.info("Forensics API stopped")


app = FastAPI(
    title="Forensics API",
    description="Blockchain transaction tracer — magisterka prototype",
    version=__version__,
    lifespan=lifespan,
)

# CORS: pozwala frontendowi (localhost:3000) wolac backend (localhost:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "service": "forensics", "version": __version__}


@app.post("/api/trace", response_model=TraceResult)
async def trace(request: TraceRequest) -> TraceResult:
    """Pobierz transakcje (ETH + ERC-20) dla adresu + etykiety z Arkham.

    Krok po kroku:
      1. Etherscan rownolegle: normalne transakcje (`txlist`) + token transfers (`tokentx`).
         Token transfers sa kluczowe bo wiekszosc ruchu z hackow to USDC/USDT/WETH.
      2. Merge + sortowanie po block_number desc, obciecie do `max_transactions`.
      3. Zbieramy unikalne adresy (root + from + to z transakcji).
      4. Arkham batch lookup: pytamy o etykiete dla kazdego adresu rownolegle.
      5. Zwracamy TraceResult z transakcjami, etykietami i notatkami.

    W kolejnych iteracjach:
      - graf BFS do `max_depth`,
      - detekcje mixerow / bridge / CEX deposit (heurystyki).
    """
    address = request.address.lower()
    half = max(request.max_transactions // 2, 25)

    try:
        normal_txs, token_txs = await asyncio.gather(
            app.state.etherscan.get_normal_transactions(address=address, offset=half),
            app.state.etherscan.get_token_transfers(address=address, offset=half),
        )
    except EtherscanError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Merge + sortuj po block_number desc, ogranicz do max
    combined = sorted(
        [*normal_txs, *token_txs],
        key=lambda t: t.block_number,
        reverse=True,
    )[: request.max_transactions]

    # Zbierz unikalne adresy do labelowania (root + from + to)
    addresses_to_label: set[str] = {address}
    for tx in combined:
        addresses_to_label.add(tx.from_address)
        if tx.to_address:
            addresses_to_label.add(tx.to_address)

    notes: list[str] = []
    labels_map: dict = {}
    try:
        labels_map = await app.state.arkham.get_many(list(addresses_to_label))
    except ArkhamError as exc:
        notes.append(f"Arkham nieaktywny: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Arkham batch failed: {}", exc)
        notes.append("Arkham batch failed (zobacz logi backendu).")

    # Heurystyki - lista rosnie z czasem.
    alerts = [
        *detect_tornado(combined, address),
        *detect_known_group(combined, address, "bridges.json", severity="warning"),
        *detect_known_group(combined, address, "cex.json", severity="warning"),
    ]
    # critical -> warning -> info na gorze
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_order.get(a.severity, 3), -a.metadata.get("last_block", 0)))

    notes.append(
        f"Etherscan: {len(normal_txs)} ETH + {len(token_txs)} ERC-20 (merged: {len(combined)}). "
        f"Arkham: {len(labels_map)} etykiet z {len(addresses_to_label)} adresow. "
        f"Heurystyki: {len(alerts)} alertow."
    )

    return TraceResult(
        root_address=address,
        transactions=combined,
        labels=list(labels_map.values()),
        alerts=alerts,
        total_transactions=len(combined),
        notes=notes,
    )
