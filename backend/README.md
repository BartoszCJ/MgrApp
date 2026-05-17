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
# API (skrocone - z auto-reloadem na port 8000)
uv run forensics serve

# z innym portem / bez reloadu
uv run forensics serve --port 8001 --no-reload

# CLI
uv run forensics --help
uv run forensics trace 0x098B716B8Aaf21512996dC57EB0615e2383E2f96 --max 20

# Alternatywnie (bez CLI, surowy uvicorn)
uv run uvicorn forensics.api:app --reload --port 8000
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
