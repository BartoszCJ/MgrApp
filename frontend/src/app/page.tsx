"use client";

import { useState } from "react";
import { trace, ApiError } from "@/lib/api";
import type { TraceResult } from "@/lib/types";

// Adres exploitera Ronin Bridge (2022, ~$625M) - jako preset dla pierwszego smoke testu.
const RONIN_EXPLOITER = "0x098B716B8Aaf21512996dC57EB0615e2383E2f96";

export default function HomePage() {
  const [address, setAddress] = useState<string>(RONIN_EXPLOITER);
  const [result, setResult] = useState<TraceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleTrace() {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await trace({ address, max_transactions: 50 });
      setResult(data);
    } catch (e) {
      if (e instanceof ApiError) setError(`API ${e.status}: ${e.message}`);
      else setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl p-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold">Forensics Blockchain Tracer</h1>
        <p className="mt-2 text-neutral-400">
          Praca magisterska — śledzenie środków po cyberatakach. MVP.
        </p>
      </header>

      <section className="mb-8 rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <label className="mb-2 block text-sm font-medium text-neutral-300">
          Adres Ethereum
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="0x..."
            className="flex-1 rounded-md border border-neutral-700 bg-neutral-950 px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={handleTrace}
            disabled={loading || !address}
            className="rounded-md bg-blue-600 px-4 py-2 font-medium hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Trace..." : "Trace"}
          </button>
        </div>
        <p className="mt-2 text-xs text-neutral-500">
          Preset: Ronin Bridge exploiter (2022, ~$625M).
        </p>
      </section>

      {error && (
        <div className="mb-8 rounded-md border border-red-800 bg-red-950 p-4 text-red-200">
          {error}
        </div>
      )}

      {result && (
        <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-semibold">
              {result.total_transactions} transakcji
            </h2>
            <code className="font-mono text-xs text-neutral-400">
              {result.root_address}
            </code>
          </div>

          {result.notes.length > 0 && (
            <ul className="mb-4 space-y-1 text-xs text-neutral-500">
              {result.notes.map((note, i) => (
                <li key={i}>· {note}</li>
              ))}
            </ul>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-800 text-left text-neutral-400">
                  <th className="py-2 pr-4 font-medium">Hash</th>
                  <th className="py-2 pr-4 font-medium">Block</th>
                  <th className="py-2 pr-4 font-medium">From</th>
                  <th className="py-2 pr-4 font-medium">To</th>
                  <th className="py-2 pr-4 text-right font-medium">ETH</th>
                </tr>
              </thead>
              <tbody>
                {result.transactions.map((tx) => (
                  <tr key={tx.hash} className="border-b border-neutral-900 font-mono text-xs">
                    <td className="py-2 pr-4">{tx.hash.slice(0, 14)}…</td>
                    <td className="py-2 pr-4">{tx.block_number}</td>
                    <td className="py-2 pr-4">{tx.from_address.slice(0, 10)}…</td>
                    <td className="py-2 pr-4">
                      {tx.to_address ? `${tx.to_address.slice(0, 10)}…` : "[contract]"}
                    </td>
                    <td className="py-2 pr-4 text-right">{tx.value_eth.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
