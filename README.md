# MgrApp — Forensics Blockchain Tracer

Praca magisterska: **Automatyczne wykrywanie i analiza aktywności transakcyjnej w blockchainie po incydentach cyberbezpieczeństwa.**

Promotor: Ruslan. Obrona: lipiec 2026.

## Struktura

Monorepo z dwoma częściami:

```
MagisterkaApp/
├── backend/    # Python: FastAPI + logika forensics
└── frontend/   # Next.js: UI do demo i obrony
```

## Quick Start

### Setup (jednorazowo)

```powershell
cd C:\Users\Bartosz\Desktop\MagisterkaApp
npm install            # instaluje 'concurrently' w roocie
npm run install:all    # instaluje deps backend (uv) + frontend (npm)
```

### Dev (codziennie)

**Jedna komenda odpalajaca backend + frontend rownolegle:**

```powershell
npm run dev
```

- Backend: http://localhost:8000 (Swagger UI: http://localhost:8000/docs)
- Frontend: http://localhost:3000

Ctrl+C zabija oba procesy naraz.

### Inne skrypty

```powershell
npm run dev:backend    # tylko backend
npm run dev:frontend   # tylko frontend
npm run build:frontend # produkcyjny build Next.js
npm run test:backend   # pytest
npm run lint:backend   # ruff check
```

## Stack

Pełne wyjaśnienie w wiki: `C:\Wiki_LLM\wiki\Tools\Magisterka Stack.md`.

- **Backend**: Python 3.11+, FastAPI, httpx, web3.py, networkx, pandas, pydantic, typer, loguru.
- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS, shadcn/ui, @xyflow/react.
- **Źródła danych**: Arkham API, Etherscan, Alchemy/Infura.
