"""FastAPI app — REST API dla frontendu.

Co to robi:
- wystawia endpointy HTTP do ktorych gada frontend,
- konfiguruje CORS zeby Next.js mogl wolac z innego portu,
- dokumentacja automatycznie pod /docs (Swagger UI).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from forensics import __version__
from forensics.clients.etherscan import EtherscanClient, EtherscanError
from forensics.config import settings
from forensics.core.models import TraceRequest, TraceResult


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Setup i cleanup zasobow przy starcie/zakonczeniu serwera."""
    logger.info("Forensics API starting (v{})", __version__)
    app.state.etherscan = EtherscanClient()
    yield
    await app.state.etherscan.close()
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
    """Pobierz transakcje dla adresu (smoke test — bez heurystyk na razie).

    To jest minimalny endpoint, ktory zwraca surowe transakcje z Etherscan.
    W kolejnych iteracjach dolozymy:
      - graf BFS do `max_depth`,
      - etykiety z Arkham,
      - detekcje mixerow / bridge / CEX deposit.
    """
    try:
        txs = await app.state.etherscan.get_normal_transactions(
            address=request.address.lower(),
            offset=request.max_transactions,
        )
    except EtherscanError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return TraceResult(
        root_address=request.address.lower(),
        transactions=txs,
        labels=[],
        total_transactions=len(txs),
        notes=[
            "MVP: na razie tylko bezposrednie transakcje z Etherscan.",
            "W kolejnych iteracjach: Arkham labels, graf BFS, heurystyki.",
        ],
    )
