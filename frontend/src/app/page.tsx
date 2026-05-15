"use client";

import { useState } from "react";
import { trace, ApiError } from "@/lib/api";
import type { AddressLabel, Alert, TraceResult } from "@/lib/types";

// Presety - znane case studies do szybkiego testowania heurystyk.
type Preset = {
  key: string;
  label: string;
  address: string;
  description: string;
};

const PRESETS: Preset[] = [
  {
    key: "ronin",
    label: "Ronin Bridge ($625M, 2022)",
    address: "0x098B716B8Aaf21512996dC57EB0615e2383E2f96",
    description: "Lazarus Group, OFAC sanctioned. Nie uzywal Tornado - poszedl przez bridges.",
  },
  {
    key: "euler",
    label: "Euler Finance ($197M, 2023)",
    address: "0x5b94fdc888c58dad24192573bba64e718db1408c",
    description: "Klasyczny user Tornado Cash. Czesc srodkow zwrocona.",
  },
  {
    key: "nomad",
    label: "Nomad Bridge ($190M, 2022)",
    address: "0xa8c83b1b30291a3a1a118058b5445cc83041cd9d",
    description: "Free-for-all hack, dziesiatki bialych kapeluszy i napastnikow.",
  },
];

const DEFAULT_PRESET = PRESETS[0];

// Mapa kolorow badge'ow per kategoria z Arkham.
const CATEGORY_BADGE: Record<string, string> = {
  hacker: "bg-red-900/60 text-red-200 border-red-800",
  mixer: "bg-purple-900/60 text-purple-200 border-purple-800",
  bridge: "bg-amber-900/60 text-amber-200 border-amber-800",
  cex: "bg-green-900/60 text-green-200 border-green-800",
};

function categoryBadgeClass(category: string | null): string {
  if (!category) return "bg-neutral-800 text-neutral-300 border-neutral-700";
  return CATEGORY_BADGE[category.toLowerCase()] ?? "bg-blue-900/60 text-blue-200 border-blue-800";
}

const SEVERITY_STYLE: Record<Alert["severity"], { box: string; badge: string; label: string }> = {
  critical: {
    box: "border-red-700 bg-red-950/60",
    badge: "bg-red-700 text-red-50",
    label: "CRITICAL",
  },
  warning: {
    box: "border-amber-700 bg-amber-950/60",
    badge: "bg-amber-600 text-amber-50",
    label: "WARNING",
  },
  info: {
    box: "border-blue-700 bg-blue-950/60",
    badge: "bg-blue-600 text-blue-50",
    label: "INFO",
  },
};

export default function HomePage() {
  const [address, setAddress] = useState<string>(DEFAULT_PRESET.address);
  const [presetKey, setPresetKey] = useState<string>(DEFAULT_PRESET.key);
  const [result, setResult] = useState<TraceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function applyPreset(key: string) {
    const preset = PRESETS.find((p) => p.key === key);
    if (!preset) return;
    setPresetKey(key);
    setAddress(preset.address);
    setResult(null);
    setError(null);
  }

  const currentPreset = PRESETS.find((p) => p.key === presetKey);

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

  // Indeksuj labels po adresie do szybkiego lookupu.
  const labelByAddress: Map<string, AddressLabel> = new Map(
    (result?.labels ?? []).map((l) => [l.address.toLowerCase(), l]),
  );

  function renderAddress(addr: string | null): React.ReactNode {
    if (!addr) return <span className="text-neutral-500">[contract]</span>;
    const label = labelByAddress.get(addr.toLowerCase());
    if (!label) {
      return <span className="font-mono">{addr.slice(0, 10)}…</span>;
    }
    return (
      <span className="flex items-center gap-2">
        <span
          className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${categoryBadgeClass(
            label.category,
          )}`}
        >
          {label.category ?? "labeled"}
        </span>
        <span title={addr}>{label.label ?? label.entity ?? addr.slice(0, 10) + "…"}</span>
      </span>
    );
  }

  return (
    <main className="mx-auto max-w-6xl p-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold">Forensics Blockchain Tracer</h1>
        <p className="mt-2 text-neutral-400">
          Praca magisterska — śledzenie środków po cyberatakach. MVP + Arkham labels.
        </p>
      </header>

      <section className="mb-8 rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <label className="mb-2 block text-sm font-medium text-neutral-300">Case study</label>
        <div className="mb-4 flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.key}
              onClick={() => applyPreset(preset.key)}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition ${
                presetKey === preset.key
                  ? "border-blue-500 bg-blue-600 text-white"
                  : "border-neutral-700 bg-neutral-950 text-neutral-300 hover:border-neutral-500"
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <label className="mb-2 block text-sm font-medium text-neutral-300">Adres Ethereum</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={address}
            onChange={(e) => {
              setAddress(e.target.value);
              setPresetKey(""); // custom address
            }}
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
        {currentPreset && (
          <p className="mt-2 text-xs text-neutral-500">{currentPreset.description}</p>
        )}
      </section>

      {error && (
        <div className="mb-8 rounded-md border border-red-800 bg-red-950 p-4 text-red-200">
          {error}
        </div>
      )}

      {result && (
        <>
          {result.alerts.length > 0 && (
            <section className="mb-8 space-y-3">
              <h2 className="text-lg font-semibold">
                Alerty z heurystyk ({result.alerts.length})
              </h2>
              {result.alerts.map((alert, i) => {
                const style = SEVERITY_STYLE[alert.severity] ?? SEVERITY_STYLE.info;
                return (
                  <div
                    key={`${alert.type}-${i}`}
                    className={`rounded-lg border p-4 ${style.box}`}
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${style.badge}`}
                      >
                        {style.label}
                      </span>
                      <span className="text-sm font-semibold">{alert.title}</span>
                    </div>
                    <p className="text-xs text-neutral-300">{alert.message}</p>
                    {alert.related_addresses.length > 0 && (
                      <p className="mt-2 truncate font-mono text-[10px] text-neutral-500">
                        addr: {alert.related_addresses.join(", ")}
                      </p>
                    )}
                    {alert.related_tx_hashes.length > 0 && (
                      <p className="truncate font-mono text-[10px] text-neutral-500">
                        tx: {alert.related_tx_hashes.slice(0, 3).join(", ")}
                        {alert.related_tx_hashes.length > 3 ? "…" : ""}
                      </p>
                    )}
                  </div>
                );
              })}
            </section>
          )}

          {result.labels.length > 0 && (
            <section className="mb-8 rounded-lg border border-neutral-800 bg-neutral-900 p-6">
              <h2 className="mb-3 text-lg font-semibold">
                Etykiety z Arkham ({result.labels.length})
              </h2>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {result.labels.map((l) => (
                  <div
                    key={l.address}
                    className="flex items-center gap-3 rounded-md border border-neutral-800 bg-neutral-950 p-3"
                  >
                    <span
                      className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${categoryBadgeClass(
                        l.category,
                      )}`}
                    >
                      {l.category ?? "labeled"}
                    </span>
                    <div className="flex-1 overflow-hidden">
                      <div className="truncate text-sm font-medium">
                        {l.label ?? l.entity ?? "(no name)"}
                      </div>
                      <div className="truncate font-mono text-xs text-neutral-500">{l.address}</div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-semibold">{result.total_transactions} transakcji</h2>
              <code className="font-mono text-xs text-neutral-400">{result.root_address}</code>
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
                    <th className="py-2 pr-4 text-right font-medium">Value</th>
                    <th className="py-2 pr-4 text-left font-medium">Token</th>
                  </tr>
                </thead>
                <tbody>
                  {result.transactions.map((tx) => (
                    <tr key={`${tx.hash}-${tx.token_contract ?? "eth"}-${tx.from_address}-${tx.to_address}`} className="border-b border-neutral-900 text-xs">
                      <td className="py-2 pr-4 font-mono">{tx.hash.slice(0, 14)}…</td>
                      <td className="py-2 pr-4 font-mono">{tx.block_number}</td>
                      <td className="py-2 pr-4">{renderAddress(tx.from_address)}</td>
                      <td className="py-2 pr-4">{renderAddress(tx.to_address)}</td>
                      <td className="py-2 pr-4 text-right font-mono">
                        {tx.value_eth.toLocaleString("en-US", {
                          maximumFractionDigits: 4,
                        })}
                      </td>
                      <td className="py-2 pr-4">
                        {tx.token_symbol ? (
                          <span className="rounded-md border border-blue-800 bg-blue-900/40 px-2 py-0.5 text-[10px] font-semibold text-blue-200">
                            {tx.token_symbol}
                          </span>
                        ) : (
                          <span className="text-neutral-500">ETH</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
