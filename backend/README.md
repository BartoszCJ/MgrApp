# Backend

Python + FastAPI. Logika forensics, klienty API, endpointy REST.

## Setup

```powershell
# 1. Zainstaluj uv jesli nie masz
# https://docs.astral.sh/uv/
# powershell: irm https://astral.sh/uv/install.ps1 | iex

# 2. Stworz srodowisko i zainstaluj zaleznosci
uv sync

# 3. Skopiuj .env.example -> .env i wpisz klucze API
copy .env.example .env
# (edytuj .env)
```

## Uruchomienie

```powershell
# API
uv run uvicorn forensics.api:app --reload --port 8000

# CLI (na razie tylko hello, beda dalsze komendy)
uv run forensics --help
```

## Struktura

```
backend/
├── pyproject.toml
├── .env.example       # szablon zmiennych srodowiskowych
└── src/forensics/
    ├── __init__.py
    ├── api.py         # FastAPI app i endpointy
    ├── cli.py         # CLI przez typer
    ├── config.py      # ladowanie .env przez pydantic-settings
    ├── clients/
    │   ├── __init__.py
    │   └── etherscan.py
    └── core/
        ├── __init__.py
        └── models.py  # pydantic modele Transaction, Address, TraceResult
```
