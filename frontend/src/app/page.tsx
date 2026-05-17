"use client";

import { useMemo, useState } from "react";
import { trace, ApiError } from "@/lib/api";
import type { AddressLabel, Alert, TraceResult } from "@/lib/types";
import { TraceGraphView, type GraphFilter } from "@/components/TraceGraphView";

// ============================================================================
// Presety
// ============================================================================

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

// ============================================================================
// Zakładki
// ============================================================================

type TabKey = "overview" | "graph" | "alerts" | "transactions" | "labels";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "graph", label: "Graph" },
  { key: "alerts", label: "Alerts" },
  { key: "transactions", label: "Transactions" },
  { key: "labels", label: "Labels" },
];

// ============================================================================
// Style: kategorie / severity
// ============================================================================

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

// ============================================================================
// Helpers
// ============================================================================

function shortAddr(addr: string | null | undefined): string {
  if (!addr) return "—";
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

// ============================================================================
// Tab: Overview
// ============================================================================

function OverviewTab({
  result,
  labelByAddress,
}: {
  result: TraceResult;
  labelByAddress: Map<string, AddressLabel>;
}) {
  const rootLabel = labelByAddress.get(result.root_address.toLowerCase());
  const counts = {
    critical: result.alerts.filter((a) => a.severity === "critical").length,
    warning: result.alerts.filter((a) => a.severity === "warning").length,
    info: result.alerts.filter((a) => a.severity === "info").length,
  };

  // Top adresy: ile razy adres pojawił sie w transakcjach jako counterparty (nie root)
  const root = result.root_address.toLowerCase();
  const counterpartyCount = new Map<string, number>();
  for (const tx of result.transactions) {
    const from = tx.from_address.toLowerCase();
    const to = (tx.to_address || "").toLowerCase();
    if (from && from !== root) counterpartyCount.set(from, (counterpartyCount.get(from) ?? 0) + 1);
    if (to && to !== root) counterpartyCount.set(to, (counterpartyCount.get(to) ?? 0) + 1);
  }
  const topCounterparties = Array.from(counterpartyCount.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Hero: root + label */}
      <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
        <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">Root address</div>
        <div className="flex flex-wrap items-center gap-3">
          {rootLabel && (
            <span
              className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase ${categoryBadgeClass(
                rootLabel.category,
              )}`}
            >
              {rootLabel.category ?? "labeled"}
            </span>
          )}
          <span className="text-xl font-semibold">
            {rootLabel?.label ?? rootLabel?.entity ?? "(unlabeled)"}
          </span>
        </div>
        <div className="mt-2 font-mono text-xs text-neutral-500">{result.root_address}</div>
      </section>

      {/* Stat cards */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard label="Transakcje" value={result.total_transactions} accent="text-neutral-100" />
        <StatCard label="Etykiety" value={result.labels.length} accent="text-blue-300" />
        <StatCard label="Critical" value={counts.critical} accent="text-red-400" />
        <StatCard label="Warning" value={counts.warning} accent="text-amber-400" />
        <StatCard label="Info" value={counts.info} accent="text-blue-400" />
      </section>

      {/* Top alerty */}
      {result.alerts.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-400">
            Najwazniejsze alerty
          </h3>
          <div className="space-y-2">
            {result.alerts.slice(0, 3).map((alert, i) => {
              const style = SEVERITY_STYLE[alert.severity] ?? SEVERITY_STYLE.info;
              return (
                <div
                  key={`${alert.type}-${i}`}
                  className={`rounded-lg border p-3 ${style.box}`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${style.badge}`}
                    >
                      {style.label}
                    </span>
                    <span className="text-sm font-medium">{alert.title}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Top counterparties */}
      {topCounterparties.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-400">
            Top adresy z ktorymi root mial kontakt
          </h3>
          <div className="space-y-2">
            {topCounterparties.map(([addr, count]) => {
              const label = labelByAddress.get(addr);
              return (
                <div
                  key={addr}
                  className="flex items-center gap-3 rounded-md border border-neutral-800 bg-neutral-950 p-3"
                >
                  {label && (
                    <span
                      className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase ${categoryBadgeClass(
                        label.category,
                      )}`}
                    >
                      {label.category ?? "labeled"}
                    </span>
                  )}
                  <div className="flex-1 overflow-hidden">
                    <div className="truncate text-sm font-medium">
                      {label?.label ?? label?.entity ?? shortAddr(addr)}
                    </div>
                    <div className="truncate font-mono text-[10px] text-neutral-500">{addr}</div>
                  </div>
                  <div className="text-xs text-neutral-400">{count} tx</div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Backend notes */}
      {result.notes.length > 0 && (
        <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Backend notes
          </h3>
          <ul className="space-y-1 text-xs text-neutral-400">
            {result.notes.map((note, i) => (
              <li key={i}>· {note}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${accent}`}>{value}</div>
    </div>
  );
}

// ============================================================================
// Tab: Graph
// ============================================================================

function GraphTab({
  result,
  labelByAddress,
}: {
  result: TraceResult;
  labelByAddress: Map<string, AddressLabel>;
}) {
  const [filter, setFilter] = useState<GraphFilter>("interesting");

  if (!result.graph || result.graph.nodes.length <= 1) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-8 text-center text-neutral-400">
        Brak grafu - moze hops=1 albo Etherscan nie zwrocil tx?
      </div>
    );
  }

  const filters: { key: GraphFilter; label: string; desc: string }[] = [
    {
      key: "interesting",
      label: "Interesting",
      desc: "root + etykiety + endpointy + top 12 hop 1",
    },
    { key: "labeled", label: "Labeled", desc: "tylko z etykieta Arkham" },
    { key: "all", label: "All", desc: "wszystkie wezly" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-400">
        <div>
          <span className="font-semibold text-neutral-200">{result.graph.nodes.length}</span>{" "}
          węzłów ·{" "}
          <span className="font-semibold text-neutral-200">{result.graph.edges.length}</span>{" "}
          krawędzi · hops:{" "}
          <span className="font-semibold text-neutral-200">{result.graph.hops}</span> ·{" "}
          <span className="font-semibold text-neutral-200">{result.graph.fetched_addresses}</span>{" "}
          adresów zapytanych
        </div>
        <div className="flex flex-wrap gap-2 text-[10px]">
          <LegendItem color="bg-blue-900 border-blue-400" label="root" />
          <LegendItem color="bg-red-950 border-red-500" label="hacker" />
          <LegendItem color="bg-purple-950 border-purple-500" label="mixer" />
          <LegendItem color="bg-amber-950 border-amber-500" label="bridge" />
          <LegendItem color="bg-green-950 border-green-500" label="cex" />
          <LegendItem color="bg-neutral-800 border-neutral-600" label="unknown" />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-neutral-500">Filtr:</span>
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            title={f.desc}
            className={`rounded-md border px-3 py-1 font-medium transition ${
              filter === f.key
                ? "border-blue-500 bg-blue-600 text-white"
                : "border-neutral-700 bg-neutral-950 text-neutral-300 hover:border-neutral-500"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <TraceGraphView graph={result.graph} labelByAddress={labelByAddress} filter={filter} />
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`inline-block h-3 w-3 rounded border ${color}`} />
      <span>{label}</span>
    </span>
  );
}

// ============================================================================
// Tab: Alerts
// ============================================================================

function AlertsTab({ result }: { result: TraceResult }) {
  if (result.alerts.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-8 text-center text-neutral-400">
        Brak alertow z heurystyk. Sledzony adres nie mial kontaktu z Tornado Cash, znanymi
        bridges ani CEX.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {result.alerts.map((alert, i) => {
        const style = SEVERITY_STYLE[alert.severity] ?? SEVERITY_STYLE.info;
        return (
          <div key={`${alert.type}-${i}`} className={`rounded-lg border p-4 ${style.box}`}>
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
    </div>
  );
}

// ============================================================================
// Tab: Transactions
// ============================================================================

function TransactionsTab({
  result,
  labelByAddress,
}: {
  result: TraceResult;
  labelByAddress: Map<string, AddressLabel>;
}) {
  function renderAddress(addr: string | null) {
    if (!addr) return <span className="text-neutral-500">[contract]</span>;
    const label = labelByAddress.get(addr.toLowerCase());
    if (!label) return <span className="font-mono">{shortAddr(addr)}</span>;
    return (
      <span className="flex items-center gap-2">
        <span
          className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase ${categoryBadgeClass(
            label.category,
          )}`}
        >
          {label.category ?? "labeled"}
        </span>
        <span title={addr}>{label.label ?? label.entity ?? shortAddr(addr)}</span>
      </span>
    );
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-6">
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
            {result.transactions.map((tx, idx) => (
              <tr
                key={`${idx}-${tx.hash}-${tx.token_contract ?? "eth"}-${tx.from_address}-${tx.to_address}`}
                className="border-b border-neutral-900 text-xs"
              >
                <td className="py-2 pr-4 font-mono">{tx.hash.slice(0, 14)}…</td>
                <td className="py-2 pr-4 font-mono">{tx.block_number}</td>
                <td className="py-2 pr-4">{renderAddress(tx.from_address)}</td>
                <td className="py-2 pr-4">{renderAddress(tx.to_address)}</td>
                <td className="py-2 pr-4 text-right font-mono">
                  {tx.value_eth.toLocaleString("en-US", { maximumFractionDigits: 4 })}
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
    </div>
  );
}

// ============================================================================
// Tab: Labels
// ============================================================================

function LabelsTab({ result }: { result: TraceResult }) {
  const [filter, setFilter] = useState<string>("all");

  const categories = useMemo(() => {
    const set = new Set<string>();
    result.labels.forEach((l) => l.category && set.add(l.category));
    return ["all", ...Array.from(set).sort()];
  }, [result.labels]);

  const filtered = useMemo(() => {
    if (filter === "all") return result.labels;
    return result.labels.filter((l) => l.category === filter);
  }, [result.labels, filter]);

  if (result.labels.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-8 text-center text-neutral-400">
        Brak etykiet z Arkham dla tego trace.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`rounded-md border px-3 py-1 text-xs font-medium transition ${
              filter === cat
                ? "border-blue-500 bg-blue-600 text-white"
                : "border-neutral-700 bg-neutral-950 text-neutral-300 hover:border-neutral-500"
            }`}
          >
            {cat}{" "}
            {cat !== "all" && (
              <span className="ml-1 text-[10px] opacity-60">
                {result.labels.filter((l) => l.category === cat).length}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {filtered.map((l) => (
          <div
            key={l.address}
            className="flex items-center gap-3 rounded-md border border-neutral-800 bg-neutral-900 p-3"
          >
            <span
              className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase ${categoryBadgeClass(
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
    </div>
  );
}

// ============================================================================
// Main page
// ============================================================================

export default function HomePage() {
  const [address, setAddress] = useState<string>(DEFAULT_PRESET.address);
  const [presetKey, setPresetKey] = useState<string>(DEFAULT_PRESET.key);
  const [hops, setHops] = useState<number>(2);
  const [result, setResult] = useState<TraceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");

  function applyPreset(key: string) {
    const preset = PRESETS.find((p) => p.key === key);
    if (!preset) return;
    setPresetKey(key);
    setAddress(preset.address);
    setResult(null);
    setError(null);
  }

  async function handleTrace() {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await trace({ address, hops, max_transactions: 50, max_per_hop: 20 });
      setResult(data);
      setActiveTab("overview");
    } catch (e) {
      if (e instanceof ApiError) setError(`API ${e.status}: ${e.message}`);
      else setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const currentPreset = PRESETS.find((p) => p.key === presetKey);

  const labelByAddress: Map<string, AddressLabel> = useMemo(() => {
    return new Map((result?.labels ?? []).map((l) => [l.address.toLowerCase(), l]));
  }, [result]);

  const tabCounts: Record<TabKey, number | null> = {
    overview: null,
    graph: null,
    alerts: result?.alerts.length ?? 0,
    transactions: result?.total_transactions ?? 0,
    labels: result?.labels.length ?? 0,
  };

  return (
    <div className="min-h-screen">
      {/* ===== STICKY HEADER ===== */}
      <header className="sticky top-0 z-20 border-b border-neutral-800 bg-neutral-950/95 backdrop-blur">
        <div className="mx-auto max-w-6xl px-6 py-4">
          <div className="mb-3 flex items-baseline justify-between">
            <h1 className="text-xl font-bold">Forensics Blockchain Tracer</h1>
            <span className="text-xs text-neutral-500">magisterka MVP</span>
          </div>

          <div className="mb-3 flex flex-wrap gap-2">
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

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={address}
              onChange={(e) => {
                setAddress(e.target.value);
                setPresetKey("");
              }}
              placeholder="0x... adres Ethereum"
              className="min-w-0 flex-1 rounded-md border border-neutral-700 bg-neutral-950 px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none"
            />

            {/* Segmented control: liczba hopów BFS */}
            <div className="flex items-center gap-2 rounded-md border border-neutral-700 bg-neutral-950 px-2 py-1">
              <span className="text-[10px] uppercase tracking-wide text-neutral-500">hops</span>
              {[1, 2, 3].map((n) => (
                <button
                  key={n}
                  onClick={() => setHops(n)}
                  className={`rounded px-2 py-1 text-xs font-semibold transition ${
                    hops === n
                      ? "bg-blue-600 text-white"
                      : "text-neutral-400 hover:text-neutral-200"
                  }`}
                  title={
                    n === 1
                      ? "Tylko tx adresu (najszybsze, ~5 sek)"
                      : n === 2
                        ? "Adres + kontrahenci (default, ~10-30 sek)"
                        : "Pelne sledzenie 3 poziomy (1-5 min, duzo zapytan)"
                  }
                >
                  {n}
                </button>
              ))}
            </div>

            <button
              onClick={handleTrace}
              disabled={loading || !address}
              className="rounded-md bg-blue-600 px-5 py-2 text-sm font-medium hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Trace..." : "Trace"}
            </button>
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
            {currentPreset && <span>{currentPreset.description}</span>}
            <span>
              {hops === 1 && "1 hop ≈ 5 sek"}
              {hops === 2 && "2 hops ≈ 10-30 sek"}
              {hops === 3 && "3 hops ≈ 1-5 min, sporo zapytan do Etherscan"}
            </span>
          </div>
        </div>

        {/* ===== TABS NAV (część stickiej części) ===== */}
        {result && (
          <nav className="mx-auto max-w-6xl px-6">
            <div className="flex gap-1 overflow-x-auto">
              {TABS.map((tab) => {
                const count = tabCounts[tab.key];
                const isActive = activeTab === tab.key;
                return (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={`whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium transition ${
                      isActive
                        ? "border-blue-500 text-blue-300"
                        : "border-transparent text-neutral-400 hover:text-neutral-200"
                    }`}
                  >
                    {tab.label}
                    {count !== null && (
                      <span className="ml-2 rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">
                        {count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </nav>
        )}
      </header>

      {/* ===== CONTENT ===== */}
      <main className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <div className="mb-6 rounded-md border border-red-800 bg-red-950 p-4 text-red-200">
            {error}
          </div>
        )}

        {!result && !loading && !error && (
          <div className="rounded-lg border border-dashed border-neutral-700 bg-neutral-900 p-12 text-center">
            <div className="mb-3 text-4xl">🔍</div>
            <h3 className="mb-2 text-lg font-semibold">Wybierz case study lub wpisz adres</h3>
            <p className="text-sm text-neutral-400">
              Kliknij jeden z presetow u gory albo wklej dowolny adres Ethereum (0x...) i nacisnij
              Trace.
            </p>
          </div>
        )}

        {loading && (
          <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-8 text-center text-neutral-400">
            Pobieranie z Etherscan + Arkham + uruchamianie heurystyk…
          </div>
        )}

        {result && (
          <>
            {activeTab === "overview" && (
              <OverviewTab result={result} labelByAddress={labelByAddress} />
            )}
            {activeTab === "graph" && (
              <GraphTab result={result} labelByAddress={labelByAddress} />
            )}
            {activeTab === "alerts" && <AlertsTab result={result} />}
            {activeTab === "transactions" && (
              <TransactionsTab result={result} labelByAddress={labelByAddress} />
            )}
            {activeTab === "labels" && <LabelsTab result={result} />}
          </>
        )}
      </main>
    </div>
  );
}
