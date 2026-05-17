"""CLI przez typer.

Co to robi:
- pozwala odpalic forensics z linii komend bez stawiania serwera,
- przyklad: `uv run forensics trace 0xABC --max 50`,
- przyda sie do batchowych eksperymentow na case studies.
"""

import asyncio

import typer
from loguru import logger

from forensics.clients.etherscan import EtherscanClient

app = typer.Typer(help="Forensics — blockchain tracer")


@app.command()
def trace(
    address: str = typer.Argument(..., help="Adres Ethereum (0x...)"),
    max_txs: int = typer.Option(20, "--max", "-n", help="Ile transakcji pobrac"),
) -> None:
    """Pobierz ostatnie transakcje adresu i wypisz w konsoli."""

    async def _run() -> None:
        client = EtherscanClient()
        try:
            txs = await client.get_normal_transactions(address.lower(), offset=max_txs)
        finally:
            await client.close()

        logger.info("Pobrano {} transakcji dla {}", len(txs), address)
        for tx in txs:
            logger.info(
                "  {} | {} -> {} | {:.4f} ETH",
                tx.hash[:12],
                tx.from_address[:10],
                (tx.to_address or "[contract]")[:10],
                tx.value_eth,
            )

    asyncio.run(_run())


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Adres na ktorym sluchamy"),
    port: int = typer.Option(8000, "--port", "-p", help="Port"),
    reload: bool = typer.Option(True, "--reload/--no-reload", help="Auto-reload przy zmianie kodu"),
) -> None:
    """Odpal serwer FastAPI (uvicorn). Skrot na `uv run uvicorn forensics.api:app --reload`."""
    import uvicorn

    uvicorn.run(
        "forensics.api:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def version() -> None:
    """Wypisz wersje."""
    from forensics import __version__

    typer.echo(f"forensics {__version__}")


if __name__ == "__main__":
    app()
