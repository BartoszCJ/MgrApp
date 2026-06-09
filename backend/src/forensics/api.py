"""FastAPI app — REST API dla frontendu.

Co to robi:
- wystawia endpointy HTTP do ktorych gada frontend,
- konfiguruje CORS zeby Next.js mogl wolac z innego portu,
- dokumentacja automatycznie pod /docs (Swagger UI).
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from forensics import __version__, cache
from forensics.clients.arkham import ArkhamClient, ArkhamError
from forensics.clients.etherscan import EtherscanClient, EtherscanError
from forensics.config import settings
from forensics.core.graph import build_trace_graph
from forensics.core.models import (
    ExperimentSaveRequest,
    ExperimentSaveResult,
    TraceRequest,
    TraceResult,
)
from forensics.experiments import write_experiment
from forensics.heuristics.known_address import detect_known_group
from forensics.heuristics.peel_chain import detect_peel_chain
from forensics.heuristics.tornado import detect_tornado
from forensics.metrics import GroundTruthError, compute_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Setup i cleanup zasobow przy starcie/zakonczeniu serwera."""
    logger.info("Forensics API starting (v{})", __version__)
    app.state.etherscan = EtherscanClient()
    app.state.arkham = ArkhamClient()
    await _run_startup_api_checks(app)
    yield
    await app.state.etherscan.close()
    await app.state.arkham.close()
    logger.info("Forensics API stopped")


async def _run_startup_api_checks(app: FastAPI) -> None:
    """Wypisz w konsoli szybkie sprawdzenie zewnetrznych API."""
    logger.info("API check | Start")
    await app.state.etherscan.check_connection()
    await app.state.arkham.check_connection()
    logger.info("API check | Koniec")


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
    """Pobierz BFS graf przeplywu dla adresu + etykiety z Arkham + heurystyki.

    Krok po kroku:
      1. BFS przez `request.hops` poziomow - dla kazdego nowego adresu pobieramy
         tx z Etherscan (ETH + ERC-20). Znane endpointy (mixer/CEX/bridge) sa terminale.
      2. Zbieramy unikalne adresy z wszystkich poziomow.
      3. Arkham batch lookup: pytamy o etykiete dla kazdego adresu rownolegle.
      4. Heurystyki: Tornado Cash / bridges / CEX deposits na pelnym zestawie tx.
      5. Tabela transakcji w UI to nadal ostatnie N z hop 0 (zeby nie zalac UI).
    """
    address = request.address.lower()
    started_at = time.perf_counter()
    cache.begin_request(request.refresh)  # reset stat hit/miss + tryb refresh

    try:
        all_txs, graph = await build_trace_graph(
            etherscan=app.state.etherscan,
            root_address=address,
            hops=request.hops,
            root_max_tx=request.max_transactions,
            per_hop_max_tx=request.max_per_hop,
            start_block=request.start_block,
            end_block=request.end_block,
        )
    except EtherscanError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Tabela: bierzemy tx tylko dla roota (zeby tabela nie miala 2000 wierszy z hop 2+)
    root_txs = [
        tx
        for tx in all_txs
        if tx.from_address == address or (tx.to_address or "") == address
    ]
    root_txs = sorted(root_txs, key=lambda t: t.block_number, reverse=True)[
        : request.max_transactions
    ]

    # Zbierz wszystkie unikalne adresy z grafu do Arkham lookup
    addresses_to_label: set[str] = {node.address for node in graph.nodes}

    notes: list[str] = []
    labels_map: dict = {}
    if request.skip_labels:
        notes.append(
            "Arkham pominiety (skip_labels=true) - etykiety nie pobrane, "
            "metryki ich nie potrzebuja."
        )
    else:
        try:
            labels_map = await app.state.arkham.get_many(list(addresses_to_label))
        except ArkhamError as exc:
            notes.append(f"Arkham nieaktywny: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Arkham batch failed: {}", exc)
            notes.append("Arkham batch failed (zobacz logi backendu).")

    # Heurystyki na pelnym zestawie tx (caly graf, nie tylko hop 0)
    alerts = [
        *detect_tornado(all_txs, address),
        *detect_known_group(all_txs, address, "bridges.json", severity="warning"),
        *detect_known_group(all_txs, address, "cex.json", severity="warning"),
        *detect_peel_chain(all_txs, address),
    ]
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_order.get(a.severity, 3), -a.metadata.get("last_block", 0)))

    window_note = ""
    if request.start_block is not None or request.end_block is not None:
        window_note = (
            f" Okno incydentu: bloki {request.start_block or 0}-"
            f"{request.end_block or 'latest'}."
        )

    notes.append(
        f"BFS hops={request.hops}: {graph.fetched_addresses} adresow zapytanych, "
        f"{len(graph.nodes)} wezlow, {len(graph.edges)} krawedzi. "
        f"Wszystkich tx (do heurystyk): {len(all_txs)}. "
        f"Arkham: {len(labels_map)} etykiet z {len(addresses_to_label)} adresow. "
        f"Heurystyki: {len(alerts)} alertow.{window_note}"
    )

    # Staty cache za ten request (per provider) - widoczne w notes i polu cache.
    cache_stats = cache.current_stats()
    cache_mode = "refresh" if request.refresh else "normal"
    if cache_stats:
        summary = "; ".join(
            f"{prov} {b['hit']} hit / {b['miss']} miss"
            for prov, b in sorted(cache_stats.items())
        )
        notes.append(f"Cache [{cache_mode}]: {summary}")
    else:
        notes.append(f"Cache [{cache_mode}]: brak zapytan do API")

    result = TraceResult(
        root_address=address,
        transactions=root_txs,
        labels=list(labels_map.values()),
        alerts=alerts,
        graph=graph,
        total_transactions=len(root_txs),
        notes=notes,
        cache={"mode": cache_mode, "providers": cache_stats},
    )

    if request.case_name:
        latency = time.perf_counter() - started_at
        try:
            result.metrics = compute_metrics(result, request.case_name, latency)
        except GroundTruthError as exc:
            notes.append(f"Metryki niedostepne: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("compute_metrics failed for case={}: {}", request.case_name, exc)
            notes.append(f"Metryki failed: {exc}")

    return result


@app.get("/api/cache/status")
async def cache_status() -> dict:
    """Statystyki dyskowego cache: liczba plikow per provider, rozmiar, wersja."""
    return cache.status()


@app.delete("/api/cache")
async def cache_clear() -> dict:
    """Czysci dyskowy cache (backend/.cache/). NIE rusza results/ ani innych danych."""
    deleted = cache.clear()
    return {"deleted": deleted}


@app.post("/api/experiments", response_model=ExperimentSaveResult)
async def save_experiment(request: ExperimentSaveRequest) -> ExperimentSaveResult:
    """Zapisuje wynik eksperymentu (3 case'y) do results/experiments/ (json+md+csv)."""
    return write_experiment(request)
