# Frontend

Next.js 15 + React 19 + TypeScript + Tailwind 4 + @xyflow/react.

## Setup

```powershell
npm install
copy .env.example .env.local
```

## Uruchomienie

```powershell
npm run dev
```

Otworz http://localhost:3000.

Backend musi byc uruchomiony rownolegle na http://localhost:8000.

## Struktura

```
frontend/
├── package.json
├── tsconfig.json
├── next.config.ts
├── postcss.config.mjs
├── .env.example
└── src/
    ├── app/
    │   ├── layout.tsx     # globalny layout
    │   ├── page.tsx       # strona startowa: input + tabela transakcji
    │   └── globals.css    # Tailwind + base style
    └── lib/
        ├── api.ts         # typed client do backendu
        └── types.ts       # typy TS odpowiadajace pydantic modelom
```
