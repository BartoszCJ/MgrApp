"use client";

import { useMemo, useState } from "react";
import { trace, ApiError, saveExperiment, clearCache } from "@/lib/api";
import { formatBlockNumber } from "@/lib/format";
import type {
  AddressLabel,
  Alert,
  CacheInfo,
  ExperimentSaveResult,
  MetricsReport,
  TraceResult,
} from "@/lib/types";
import { TraceGraphView, type GraphFilter } from "@/components/TraceGraphView";

// ============================================================================
// Presety
// ============================================================================

type IncidentMeta = {
  date: string; // YYYY-MM-DD
  attackBlock: number;
  windowSize: number; // ile blokow post-attack zlapac (~7 dni dla 50000)
  summary: string;
};

type OsintLink = {
  label: string;
  url: string;
  source: "post-mortem" | "thread" | "report" | "sanction";
};

type Preset = {
  key: string;
  label: string;
  address: string;
  description: string;
  incident: IncidentMeta;
  osint: OsintLink[];
};

const PRESETS: Preset[] = [
  {
    key: "ronin",
    label: "Ronin Bridge ($625M, 2022)",
    address: "0x098B716B8Aaf21512996dC57EB0615e2383E2f96",
    description: "Lazarus Group, OFAC sanctioned. Laundering: Tornado Cash + bridges.",
    incident: {
      date: "2022-03-23",
      attackBlock: 14442835,
      windowSize: 50000,
      summary:
        "Lazarus skompromitowal 5 z 9 walidatorow Ronin sidechain (Axie Infinity) i wyplacil 173600 ETH + 25.5M USDC.",
    },
    osint: [
      {
        label: "Post-mortem Sky Mavis",
        url: "https://roninblockchain.substack.com/p/community-alert-ronin-validators",
        source: "post-mortem",
      },
      {
        label: "Chainalysis: Lazarus & Ronin Bridge",
        url: "https://www.chainalysis.com/blog/lazarus-group-axie-infinity-ronin-bridge-dprk/",
        source: "report",
      },
      {
        label: "US Treasury OFAC sanction",
        url: "https://home.treasury.gov/news/press-releases/jy0731",
        source: "sanction",
      },
    ],
  },
  {
    key: "euler",
    // Seed = attacker_root (Euler Finance Exploiter 1) z backend/data/ground_truth/euler.json.
    // Wczesniej byl tu adres spoza ground truth -> 0% address recall (BFS startowal ze zlego miejsca).
    label: "Euler Finance ($197M, 2023)",
    address: "0xb2698c2D99aD2c302a95a8DB26B08D17a77cEDd4",
    description: "Glowny EOA exploitera. Czesc srodkow przez Tornado, reszta zwrocona po negocjacjach.",
    incident: {
      date: "2023-03-13",
      attackBlock: 16817996,
      windowSize: 50000,
      summary:
        "Flash loan exploit na donateToReserves(). Hacker zwrocil srodki po negocjacjach w kwietniu 2023.",
    },
    osint: [
      {
        label: "Post-mortem Euler Labs",
        url: "https://medium.com/euler-protocol/eulers-public-post-mortem-1ec77f81e89e",
        source: "post-mortem",
      },
      {
        label: "ZachXBT investigation thread",
        url: "https://twitter.com/zachxbt/status/1635336760898777088",
        source: "thread",
      },
      {
        label: "SlowMist analiza",
        url: "https://slowmist.medium.com/slowmist-euler-finance-event-analysis-3aa12d9ce5b1",
        source: "report",
      },
    ],
  },
  {
    key: "nomad",
    label: "Nomad Bridge ($190M, 2022)",
    address: "0xa8c83b1b30291a3a1a118058b5445cc83041cd9d",
    description: "Free-for-all hack, dziesiatki bialych kapeluszy i napastnikow.",
    incident: {
      date: "2022-08-01",
      attackBlock: 15259101,
      windowSize: 50000,
      summary:
        "Bug w process() po upgrade pozwalal kazdemu skopiowac proven message i zmienic adres odbiorcy. Dziesiatki nasladowcow w 24h.",
    },
    osint: [
      {
        label: "Post-mortem Nomad",
        url: "https://medium.com/nomad-xyz-blog/nomad-bridge-hack-root-cause-analysis-875ad2e5aacd",
        source: "post-mortem",
      },
      {
        label: "ZachXBT thread",
        url: "https://twitter.com/zachxbt/status/1554148562054520833",
        source: "thread",
      },
      {
        label: "Halborn analiza",
        url: "https://www.halborn.com/blog/post/explained-the-nomad-hack-august-2022",
        source: "report",
      },
    ],
  },
];

const DEFAULT_PRESET = PRESETS[0];

const OSINT_SOURCE_STYLE: Record<OsintLink["source"], { badge: string; label: string }> = {
  "post-mortem": { badge: "bg-blue-900 text-blue-200 border-blue-700", label: "POST-MORTEM" },
  thread: { badge: "bg-purple-900 text-purple-200 border-purple-700", label: "THREAD" },
  report: { badge: "bg-emerald-900 text-emerald-200 border-emerald-700", label: "REPORT" },
  sanction: { badge: "bg-red-900 text-red-200 border-red-700", label: "SANCTION" },
};

// ============================================================================
// Zakładki
// ============================================================================

type TabKey = "overview" | "graph" | "alerts" | "transactions" | "labels" | "metrics";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "graph", label: "Graph" },
  { key: "alerts", label: "Alerts" },
  { key: "transactions", label: "Transactions" },
  { key: "labels", label: "Labels" },
  { key: "metrics", label: "Metrics" },
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
  preset,
}: {
  result: TraceResult;
  labelByAddress: Map<string, AddressLabel>;
  preset: Preset | undefined;
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

      {/* OSINT panel: per case study, niezalezny od backendu */}
      {preset && (
        <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-5">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-300">
              OSINT &amp; kontekst incydentu
            </h3>
            <span className="text-[10px] uppercase tracking-wider text-neutral-500">
              {preset.incident.date} · blok ataku {formatBlockNumber(preset.incident.attackBlock)}
            </span>
          </div>
          <p className="mb-4 text-xs text-neutral-300">{preset.incident.summary}</p>
          <ul className="space-y-2">
            {preset.osint.map((link) => {
              const style = OSINT_SOURCE_STYLE[link.source];
              return (
                <li key={link.url}>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-3 rounded-md border border-neutral-800 bg-neutral-950 p-2.5 transition hover:border-blue-600 hover:bg-neutral-900"
                  >
                    <span
                      className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${style.badge}`}
                    >
                      {style.label}
                    </span>
                    <span className="flex-1 truncate text-sm text-neutral-200">{link.label}</span>
                    <span className="text-[10px] text-neutral-500">↗</span>
                  </a>
                </li>
              );
            })}
          </ul>
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
      <div className="space-y-4">
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-6 text-sm text-amber-100">
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded bg-amber-700 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-50">
              Arkham off
            </span>
            <span className="font-medium">Brak etykiet z Arkham Intelligence</span>
          </div>
          <p className="mb-2 text-amber-200">
            Free tier Arkham API zostal wyczerpany. Endpoint nie zwraca etykiet
            adresow (nazwy typu &quot;Binance Hot Wallet 7&quot;).
          </p>
          <p className="text-xs text-amber-300/80">
            W pracy mgr to realistyczne ograniczenie: komercyjne narzedzia
            forensics (Chainalysis, Elliptic) korzystaja z platnych warstw
            atrybucji. Prototyp dziala niezaleznie od Arkhama dzieki lokalnym
            heurystykom.
          </p>
        </div>

        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4 text-xs text-neutral-400">
          <p className="mb-2 font-medium text-neutral-300">Co wciaz dziala:</p>
          <ul className="space-y-1">
            <li>
              <span className="text-green-400">✓</span> Heurystyki (Tornado /
              Bridges / CEX / Peel Chain) - chodza po lokalnych listach
              <span className="font-mono text-neutral-500">
                {" "}
                data/known_addresses/*.json
              </span>
              .
            </li>
            <li>
              <span className="text-green-400">✓</span> Graf BFS przez Etherscan
              (etykiety adresow nie sa potrzebne do sledzenia przeplywu).
            </li>
            <li>
              <span className="text-green-400">✓</span> Ground truth + metryki -
              porownanie z publicznie udokumentowanymi adresami z
              <span className="font-mono text-neutral-500">
                {" "}
                data/ground_truth/*.json
              </span>
              .
            </li>
            <li>
              <span className="text-amber-400">~</span> Address Recall lekko
              nizszy bo Arkham nie dorzuca dodatkowych adresow do grafu (ale BFS
              i tak je znajduje).
            </li>
          </ul>
        </div>
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
// Tab: Metrics
// ============================================================================

// Progi kolorow per metryka. Zielony = dobry, zolty = sredni, czerwony = slaby.
function metricColor(value: number): { box: string; bar: string; text: string } {
  if (value >= 0.7) {
    return {
      box: "border-green-700 bg-green-950/40",
      bar: "bg-green-500",
      text: "text-green-300",
    };
  }
  if (value >= 0.4) {
    return {
      box: "border-amber-700 bg-amber-950/40",
      bar: "bg-amber-500",
      text: "text-amber-300",
    };
  }
  return {
    box: "border-red-700 bg-red-950/40",
    bar: "bg-red-500",
    text: "text-red-300",
  };
}

function MetricBar({
  label,
  value,
  description,
}: {
  label: string;
  value: number;
  description: string;
}) {
  const c = metricColor(value);
  const pct = Math.round(value * 100);
  return (
    <div className={`rounded-lg border p-4 ${c.box}`}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-medium text-neutral-200">{label}</span>
        <span className={`font-mono text-xl font-bold ${c.text}`}>{pct}%</span>
      </div>
      <div className="mb-2 h-2 overflow-hidden rounded-full bg-neutral-800">
        <div
          className={`h-full transition-all ${c.bar}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-neutral-400">{description}</p>
    </div>
  );
}

function MetricsTab({ result }: { result: TraceResult }) {
  const metrics: MetricsReport | null = result.metrics;

  if (!metrics) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-8 text-center text-neutral-400">
        <div className="mb-2 text-2xl">📊</div>
        <p className="text-sm">
          Brak metryk. Wybierz preset case study (Ronin/Euler/Nomad), zeby
          uruchomic ewaluacje vs ground truth.
        </p>
        <p className="mt-2 text-xs text-neutral-500">
          Trace na dowolnym adresie spoza presetow dziala normalnie, ale bez
          metryk - bo nie ma do czego porownywac.
        </p>
      </div>
    );
  }

  const b = metrics.breakdown;

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-1 flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">
            Metryki efektywnosci - case:{" "}
            <span className="font-mono text-blue-300">{metrics.case_name}</span>
          </h2>
          <span className="font-mono text-xs text-neutral-500">
            latency: {metrics.latency_seconds.toFixed(2)}s
          </span>
        </div>
        <p className="text-xs text-neutral-500">
          Porownanie wyniku trace z publicznie udokumentowanym ground truth
          (Chainalysis, Elliptic, Mandiant, Coinbase).
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <MetricBar
          label="Address Recall"
          value={metrics.address_recall}
          description={`${b.addresses_found ?? 0} z ${b.addresses_expected ?? 0} znanych adresow ground truth znalezione przez BFS (z ${b.addresses_in_trace ?? 0} adresow w grafie).`}
        />
        <MetricBar
          label="Heuristic Precision"
          value={metrics.heuristic_precision}
          description={`Ile kategorii heurystyk ktore zgłosily alert mialo do tego prawo. Falszywe alarmy: ${(b.heuristics_false_positives ?? []).join(", ") || "brak"}.`}
        />
        <MetricBar
          label="Heuristic Recall"
          value={metrics.heuristic_recall}
          description={`Trafione: ${(b.heuristics_hit ?? []).join(", ") || "brak"} / oczekiwane: ${(b.heuristics_expected ?? []).join(", ") || "brak"}.`}
        />
        <MetricBar
          label="CEX Coverage"
          value={metrics.cex_coverage}
          description={`Udokumentowane adresy CEX-deposit (ground truth) osiagniete przez BFS: ${b.cex_destination_addresses_found ?? 0}/${b.cex_destination_addresses_expected ?? 0}. Gieldy: ${(b.cex_destination_exchanges_found ?? []).join(", ") || "brak"} / oczekiwane: ${(b.cex_destination_exchanges_expected ?? []).join(", ") || "brak"}.`}
        />
      </div>

      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
        <h3 className="mb-3 text-sm font-semibold text-neutral-200">Breakdown</h3>
        <dl className="grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2">
          <div className="flex justify-between border-b border-neutral-800 pb-2">
            <dt className="text-neutral-400">Adresy znalezione / oczekiwane</dt>
            <dd className="font-mono text-neutral-200">
              {b.addresses_found ?? 0} / {b.addresses_expected ?? 0}
            </dd>
          </div>
          <div className="flex justify-between border-b border-neutral-800 pb-2">
            <dt className="text-neutral-400">Adresy w grafie BFS (total)</dt>
            <dd className="font-mono text-neutral-200">{b.addresses_in_trace ?? 0}</dd>
          </div>
          <div className="flex justify-between border-b border-neutral-800 pb-2">
            <dt className="text-neutral-400">Heurystyki trafione</dt>
            <dd className="font-mono text-neutral-200">
              {(b.heuristics_hit ?? []).length} / {(b.heuristics_expected ?? []).length}
            </dd>
          </div>
          <div className="flex justify-between border-b border-neutral-800 pb-2">
            <dt className="text-neutral-400">CEX adresy (ground truth)</dt>
            <dd className="font-mono text-neutral-200">
              {b.cex_destination_addresses_found ?? 0} /{" "}
              {b.cex_destination_addresses_expected ?? 0}
            </dd>
          </div>
        </dl>
        {((b.heuristics_missing ?? []).length > 0 ||
          (b.heuristics_false_positives ?? []).length > 0) && (
          <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
            {(b.heuristics_missing ?? []).length > 0 && (
              <div className="rounded border border-amber-800 bg-amber-950/40 p-2">
                <div className="mb-1 text-amber-300">Brakujace heurystyki:</div>
                <div className="font-mono text-amber-200">
                  {(b.heuristics_missing ?? []).join(", ")}
                </div>
              </div>
            )}
            {(b.heuristics_false_positives ?? []).length > 0 && (
              <div className="rounded border border-red-800 bg-red-950/40 p-2">
                <div className="mb-1 text-red-300">Falszywe alarmy:</div>
                <div className="font-mono text-red-200">
                  {(b.heuristics_false_positives ?? []).join(", ")}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {metrics.notes.length > 0 && (
        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <h3 className="mb-2 text-sm font-semibold text-neutral-200">Uwagi</h3>
          <ul className="space-y-1 text-xs text-neutral-400">
            {metrics.notes.map((note, idx) => (
              <li key={idx} className="flex gap-2">
                <span className="text-neutral-600">•</span>
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4 text-xs text-neutral-500">
        <p className="mb-1 font-medium text-neutral-400">Jak czytac te liczby?</p>
        <ul className="space-y-1">
          <li>
            <span className="text-green-400">≥70%</span> dobry wynik,{" "}
            <span className="text-amber-400">40-70%</span> sredni,{" "}
            <span className="text-red-400">&lt;40%</span> slaby.
          </li>
          <li>
            <strong>Address Recall</strong> bywa niski - publicznie znamy ~30 adresow z
            12000+ ktore Lazarus uzyl. Ground truth to dolne ograniczenie.
          </li>
          <li>
            <strong>Heuristic Precision</strong> 100% gdy zaden falszywy alarm. Patrz
            uwagi nizej dla przykladow false positives (np. CEX dla Eulera).
          </li>
          <li>
            Gdy <strong>Arkham off</strong> (badge w headerze) - Address Recall moze
            byc lekko nizszy, bo etykiety nie dorzucaja dodatkowych adresow do
            zbioru znalezionych. Heurystyki i ground truth dzialaja niezaleznie.
          </li>
        </ul>
      </div>
    </div>
  );
}

// ============================================================================
// Eksperyment: 3 case'y naraz -> tabela porownawcza
// ============================================================================

type ExperimentRow = {
  key: string;
  label: string;
  address: string;
  startBlock: number | null;
  endBlock: number | null;
  hops: number;
  metrics: MetricsReport | null;
  nodes: number;
  edges: number;
  alerts: number;
  labels: number;
  cache: CacheInfo;
  error: string | null;
};

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function buildExperimentMarkdown(rows: ExperimentRow[], hopsUsed: number): string {
  const head =
    "| Case | Address Recall | Heur. Precision | Heur. Recall | CEX Coverage | Węzły | Alerty | Latency [s] |";
  const sep = "|---|---|---|---|---|---|---|---|";
  const body = rows.map((r) =>
    r.metrics
      ? `| ${r.label} | ${pct(r.metrics.address_recall)} | ${pct(r.metrics.heuristic_precision)} | ` +
        `${pct(r.metrics.heuristic_recall)} | ${pct(r.metrics.cex_coverage)} | ${r.nodes} | ` +
        `${r.alerts} | ${r.metrics.latency_seconds.toFixed(2)} |`
      : `| ${r.label} | — | — | — | — | — | — | ${r.error ?? "błąd"} |`,
  );
  const stamp = `<!-- hops=${hopsUsed}, okno incydentu ON, wygenerowano ${new Date()
    .toISOString()
    .slice(0, 10)} -->`;
  return [stamp, head, sep, ...body].join("\n");
}

function buildExperimentCsv(rows: ExperimentRow[]): string {
  const head =
    "case,address_recall,heuristic_precision,heuristic_recall,cex_coverage,nodes,alerts,latency_s";
  const body = rows.map((r) =>
    r.metrics
      ? [
          r.label,
          r.metrics.address_recall,
          r.metrics.heuristic_precision,
          r.metrics.heuristic_recall,
          r.metrics.cex_coverage,
          r.nodes,
          r.alerts,
          r.metrics.latency_seconds,
        ].join(",")
      : [r.label, "", "", "", "", "", "", r.error ?? "error"].join(","),
  );
  return [head, ...body].join("\n");
}

function downloadText(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function ExperimentMetricCell({ value }: { value: number }) {
  const c = metricColor(value);
  return (
    <td className={`px-3 py-2 text-right font-mono font-semibold ${c.text}`}>{pct(value)}</td>
  );
}

function ExperimentPanel({
  rows,
  running,
  progress,
  hopsUsed,
  saveResult,
  saveError,
}: {
  rows: ExperimentRow[];
  running: boolean;
  progress: string | null;
  hopsUsed: number;
  saveResult: ExperimentSaveResult | null;
  saveError: string | null;
}) {
  const [copied, setCopied] = useState(false);

  // Srednia liczona tylko z wierszy ktore maja metryki (bez assertion - czysty TS).
  const ms: MetricsReport[] = [];
  for (const r of rows) if (r.metrics) ms.push(r.metrics);
  const avg =
    ms.length > 0
      ? {
          address_recall: ms.reduce((s, m) => s + m.address_recall, 0) / ms.length,
          heuristic_precision: ms.reduce((s, m) => s + m.heuristic_precision, 0) / ms.length,
          heuristic_recall: ms.reduce((s, m) => s + m.heuristic_recall, 0) / ms.length,
          cex_coverage: ms.reduce((s, m) => s + m.cex_coverage, 0) / ms.length,
        }
      : null;

  // Zagregowane staty cache po wszystkich case'ach (ile poszlo z cache).
  const cacheAgg: Record<string, { hit: number; miss: number }> = {};
  for (const r of rows) {
    for (const [prov, b] of Object.entries(r.cache?.providers ?? {})) {
      const acc = (cacheAgg[prov] ??= { hit: 0, miss: 0 });
      acc.hit += b.hit;
      acc.miss += b.miss;
    }
  }
  const cacheLine = Object.entries(cacheAgg)
    .map(([p, b]) => `${p}: ${b.hit} hit / ${b.miss} miss`)
    .join(" · ");

  async function copyMarkdown() {
    await navigator.clipboard.writeText(buildExperimentMarkdown(rows, hopsUsed));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Eksperyment — 3 case studies</h2>
          <p className="text-xs text-neutral-500">
            Ronin / Euler / Nomad · hops={hopsUsed} · okno incydentu ON · porownanie z ground
            truth.
          </p>
        </div>
        {!running && ms.length > 0 && (
          <div className="flex gap-2">
            <button
              onClick={copyMarkdown}
              className="rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs font-medium text-neutral-200 transition hover:border-blue-500"
            >
              {copied ? "Skopiowano ✓" : "Kopiuj Markdown"}
            </button>
            <button
              onClick={() =>
                downloadText("eksperyment_metryki.csv", buildExperimentCsv(rows), "text/csv")
              }
              className="rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs font-medium text-neutral-200 transition hover:border-blue-500"
            >
              Pobierz CSV
            </button>
          </div>
        )}
      </div>

      {running && (
        <div className="rounded-md border border-blue-900 bg-blue-950/40 p-3 text-sm text-blue-200">
          Uruchamiam… {progress ?? ""}{" "}
          <span className="text-blue-400">
            (cierpliwosci — to {PRESETS.length} pelne trace, kazdy ~{hopsUsed >= 3 ? "1-5 min" : "10-30 sek"})
          </span>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-neutral-800 bg-neutral-900">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-left text-neutral-400">
              <th className="px-3 py-2 font-medium">Case</th>
              <th className="px-3 py-2 text-right font-medium">Addr. Recall</th>
              <th className="px-3 py-2 text-right font-medium">Heur. Prec.</th>
              <th className="px-3 py-2 text-right font-medium">Heur. Recall</th>
              <th className="px-3 py-2 text-right font-medium">CEX Cov.</th>
              <th className="px-3 py-2 text-right font-medium">Węzły</th>
              <th className="px-3 py-2 text-right font-medium">Alerty</th>
              <th className="px-3 py-2 text-right font-medium">Latency</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-b border-neutral-900">
                <td className="px-3 py-2 font-medium text-neutral-200">{r.label}</td>
                {r.metrics ? (
                  <>
                    <ExperimentMetricCell value={r.metrics.address_recall} />
                    <ExperimentMetricCell value={r.metrics.heuristic_precision} />
                    <ExperimentMetricCell value={r.metrics.heuristic_recall} />
                    <ExperimentMetricCell value={r.metrics.cex_coverage} />
                    <td className="px-3 py-2 text-right font-mono text-neutral-300">{r.nodes}</td>
                    <td className="px-3 py-2 text-right font-mono text-neutral-300">{r.alerts}</td>
                    <td className="px-3 py-2 text-right font-mono text-neutral-400">
                      {r.metrics.latency_seconds.toFixed(1)}s
                    </td>
                  </>
                ) : (
                  <td colSpan={7} className="px-3 py-2 text-xs text-red-300">
                    {r.error ?? "błąd"}
                  </td>
                )}
              </tr>
            ))}
            {avg && (
              <tr className="border-t border-neutral-700 bg-neutral-950/60">
                <td className="px-3 py-2 font-semibold text-neutral-300">Średnia</td>
                <ExperimentMetricCell value={avg.address_recall} />
                <ExperimentMetricCell value={avg.heuristic_precision} />
                <ExperimentMetricCell value={avg.heuristic_recall} />
                <ExperimentMetricCell value={avg.cex_coverage} />
                <td className="px-3 py-2 text-right text-neutral-600">—</td>
                <td className="px-3 py-2 text-right text-neutral-600">—</td>
                <td className="px-3 py-2 text-right text-neutral-600">—</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {!running && cacheLine && (
        <div className="rounded-md border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-neutral-400">
          Cache (suma 3 case&apos;ow): {cacheLine}
        </div>
      )}

      {saveResult && (
        <div className="rounded-md border border-emerald-800 bg-emerald-950/40 px-3 py-2 text-xs text-emerald-200">
          Zapisano do <span className="font-mono">results/experiments/</span>:{" "}
          {saveResult.files.join(", ")}
          {saveResult.commit_hash && (
            <>
              {" "}
              · commit <span className="font-mono">{saveResult.commit_hash}</span>
            </>
          )}
        </div>
      )}
      {saveError && (
        <div className="rounded-md border border-red-800 bg-red-950/40 px-3 py-2 text-xs text-red-200">
          Zapis wynikow nieudany: {saveError}
        </div>
      )}

      <p className="text-xs text-neutral-500">
        Kolory: <span className="text-green-400">≥70%</span> dobry,{" "}
        <span className="text-amber-400">40-70%</span> sredni, <span className="text-red-400">&lt;40%</span>{" "}
        slaby. Tabela gotowa do wklejenia w rozdzial wynikow (Kopiuj Markdown) lub do dalszej
        obrobki (CSV). Graf kazdego case&apos;a obejrzysz osobno przez Trace + zakladka Graph.
      </p>
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
  const [useIncidentWindow, setUseIncidentWindow] = useState<boolean>(true);
  const [result, setResult] = useState<TraceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");

  // Tryb eksperymentu: 3 case'y naraz -> tabela. Wzajemnie wyklucza sie z trybem
  // pojedynczego trace (experiment !== null => pokazujemy panel, nie zakladki).
  const [experiment, setExperiment] = useState<ExperimentRow[] | null>(null);
  const [expRunning, setExpRunning] = useState(false);
  const [expProgress, setExpProgress] = useState<string | null>(null);
  const [expHops, setExpHops] = useState<number>(2);
  const [expSaveResult, setExpSaveResult] = useState<ExperimentSaveResult | null>(null);
  const [expSaveError, setExpSaveError] = useState<string | null>(null);

  // Cache: tryb "na zywo" (pomin cache) + zarzadzanie (wyczysc).
  const [refresh, setRefresh] = useState(false);
  const [cacheMsg, setCacheMsg] = useState<string | null>(null);
  const [clearingCache, setClearingCache] = useState(false);

  function applyPreset(key: string) {
    const preset = PRESETS.find((p) => p.key === key);
    if (!preset) return;
    setPresetKey(key);
    setAddress(preset.address);
    setUseIncidentWindow(true);
    setResult(null);
    setError(null);
  }

  async function handleTrace() {
    setLoading(true);
    setError(null);
    setResult(null);
    setExperiment(null); // wyjscie z trybu eksperymentu

    const preset = PRESETS.find((p) => p.key === presetKey);
    const incidentWindow =
      preset && useIncidentWindow
        ? {
            start_block: preset.incident.attackBlock,
            end_block: preset.incident.attackBlock + preset.incident.windowSize,
          }
        : {};

    try {
      const data = await trace({
        address,
        hops,
        max_transactions: 50,
        max_per_hop: 20,
        ...incidentWindow,
        refresh,
        // case_name: tylko gdy uzytkownik wybral preset (ronin/euler/nomad).
        // Backend ma plik ground_truth/<case_name>.json - bedziemy mieli metryki.
        case_name: preset ? preset.key : null,
      });
      setResult(data);
      setActiveTab("overview");
    } catch (e) {
      if (e instanceof ApiError) setError(`API ${e.status}: ${e.message}`);
      else setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // Eksperyment: leci po wszystkich presetach po kolei (sekwencyjnie, zeby nie
  // zalac Etherscan/Arkham), z aktualnym hops i oknem incydentu ON. Tabela
  // wypelnia sie progresywnie - kazdy gotowy case od razu pokazuje sie w UI.
  async function runExperiment() {
    setExpRunning(true);
    setExpProgress(null);
    setError(null);
    setResult(null);
    setExpHops(hops);
    setExpSaveResult(null);
    setExpSaveError(null);
    setExperiment([]);

    const rows: ExperimentRow[] = [];
    for (let i = 0; i < PRESETS.length; i++) {
      const preset = PRESETS[i];
      const startBlock = preset.incident.attackBlock;
      const endBlock = preset.incident.attackBlock + preset.incident.windowSize;
      setExpProgress(`${preset.label} (${i + 1}/${PRESETS.length})`);
      try {
        const data = await trace({
          address: preset.address,
          hops,
          max_transactions: 50,
          max_per_hop: 20,
          start_block: startBlock,
          end_block: endBlock,
          refresh,
          case_name: preset.key,
        });
        rows.push({
          key: preset.key,
          label: preset.label,
          address: preset.address,
          startBlock,
          endBlock,
          hops,
          metrics: data.metrics,
          nodes: data.graph?.nodes.length ?? 0,
          edges: data.graph?.edges.length ?? 0,
          alerts: data.alerts.length,
          labels: data.labels.length,
          cache: data.cache ?? {},
          error: data.metrics ? null : "Brak metryk (sprawdz data/ground_truth)",
        });
      } catch (e) {
        rows.push({
          key: preset.key,
          label: preset.label,
          address: preset.address,
          startBlock,
          endBlock,
          hops,
          metrics: null,
          nodes: 0,
          edges: 0,
          alerts: 0,
          labels: 0,
          cache: {},
          error: e instanceof ApiError ? `API ${e.status}: ${e.message}` : String(e),
        });
      }
      setExperiment([...rows]);
    }

    setExpProgress(null);
    setExpRunning(false);

    // Zapis na backend: results/experiments/ (json+md+csv) z metadanymi + commit_hash.
    try {
      const saved = await saveExperiment({
        cache_mode: refresh ? "refresh" : "normal",
        cases: rows.map((r) => ({
          case: r.key,
          address: r.address,
          hops: r.hops,
          start_block: r.startBlock,
          end_block: r.endBlock,
          nodes: r.nodes,
          edges: r.edges,
          alerts: r.alerts,
          labels: r.labels,
          metrics: r.metrics,
          cache: r.cache,
          error: r.error,
        })),
      });
      setExpSaveResult(saved);
    } catch (e) {
      setExpSaveError(e instanceof ApiError ? `API ${e.status}: ${e.message}` : String(e));
    }
  }

  async function handleClearCache() {
    setClearingCache(true);
    setCacheMsg(null);
    try {
      const res = await clearCache();
      setCacheMsg(`Cache wyczyszczony: usunieto ${res.deleted} plikow.`);
    } catch (e) {
      setCacheMsg(e instanceof ApiError ? `Blad: ${e.message}` : String(e));
    } finally {
      setClearingCache(false);
    }
  }

  const currentPreset = PRESETS.find((p) => p.key === presetKey);
  const windowEndBlock = currentPreset
    ? currentPreset.incident.attackBlock + currentPreset.incident.windowSize
    : null;

  const labelByAddress: Map<string, AddressLabel> = useMemo(() => {
    return new Map((result?.labels ?? []).map((l) => [l.address.toLowerCase(), l]));
  }, [result]);

  const tabCounts: Record<TabKey, number | null> = {
    overview: null,
    graph: null,
    alerts: result?.alerts.length ?? 0,
    transactions: result?.total_transactions ?? 0,
    labels: result?.labels.length ?? 0,
    metrics: result?.metrics ? 1 : null,
  };

  // Arkham off: heurystyka prosta - po trace nie ma etykiet ani note o sukcesie.
  // notes zawiera "Arkham" tylko gdy bylo ERROR/empty (handler dodaje notki o bledach).
  const arkhamOff =
    result !== null &&
    result.labels.length === 0 &&
    (result.notes.some((n) => n.toLowerCase().includes("arkham")) ||
      result.transactions.length > 0);

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
              disabled={loading || expRunning || !address}
              className="rounded-md bg-blue-600 px-5 py-2 text-sm font-medium hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Trace..." : "Trace"}
            </button>

            <button
              onClick={runExperiment}
              disabled={loading || expRunning}
              title="Uruchamia Ronin + Euler + Nomad z aktualnym hops i oknem incydentu, buduje tabele porownawcza metryk do pracy"
              className="rounded-md border border-emerald-700 bg-emerald-700/20 px-4 py-2 text-sm font-medium text-emerald-200 transition hover:bg-emerald-700/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {expRunning ? "Eksperyment…" : "Eksperyment 3×"}
            </button>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
            <label
              className="flex cursor-pointer items-center gap-2 text-neutral-300"
              title="Pomija dyskowy cache i pobiera swieze dane z API (nadpisuje cache). Do pokazania, ze API zyje."
            >
              <input
                type="checkbox"
                checked={refresh}
                onChange={(e) => setRefresh(e.target.checked)}
                className="h-3.5 w-3.5 cursor-pointer accent-emerald-600"
              />
              <span>Pobierz na żywo (pomiń cache)</span>
            </label>
            <button
              onClick={handleClearCache}
              disabled={clearingCache}
              title="Usuwa dyskowy cache (backend/.cache/). Nie rusza zapisanych wynikow eksperymentow."
              className="rounded-md border border-neutral-700 bg-neutral-950 px-2.5 py-1 font-medium text-neutral-300 transition hover:border-red-600 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {clearingCache ? "Czyszczę…" : "Wyczyść cache"}
            </button>
            {cacheMsg && <span className="text-neutral-400">{cacheMsg}</span>}
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
            <div className="flex flex-wrap items-center gap-2">
              {currentPreset && <span>{currentPreset.description}</span>}
              {arkhamOff && (
                <span
                  className="rounded border border-amber-800 bg-amber-950/60 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-300"
                  title="Arkham API nieaktywne (free tier wyczerpany). Heurystyki + ground truth dzialaja niezaleznie."
                >
                  Arkham off
                </span>
              )}
            </div>
            <span>
              {hops === 1 && "1 hop ≈ 5 sek"}
              {hops === 2 && "2 hops ≈ 10-30 sek"}
              {hops === 3 && "3 hops ≈ 1-5 min, sporo zapytan do Etherscan"}
            </span>
          </div>

          {/* Okno incydentu - toggle + opis. Bez tego heurystyki dzialaja na ostatnich tx (puste). */}
          {currentPreset && windowEndBlock !== null && (
            <div className="mt-2 flex flex-wrap items-center gap-3 rounded-md border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs">
              <label className="flex cursor-pointer items-center gap-2 text-neutral-300">
                <input
                  type="checkbox"
                  checked={useIncidentWindow}
                  onChange={(e) => setUseIncidentWindow(e.target.checked)}
                  className="h-3.5 w-3.5 cursor-pointer accent-blue-600"
                />
                <span className="font-medium">Okno incydentu</span>
              </label>
              <span
                className={`flex flex-wrap items-center gap-2 ${useIncidentWindow ? "text-neutral-400" : "text-neutral-600 line-through"}`}
              >
                <span>{currentPreset.incident.date}</span>
                <span>·</span>
                <span className="font-mono">
                  bloki {formatBlockNumber(currentPreset.incident.attackBlock)}-
                  {formatBlockNumber(windowEndBlock)}
                </span>
                <span>·</span>
                <span>~{Math.round(currentPreset.incident.windowSize / 7200)} dni post-attack</span>
              </span>
              {!useIncidentWindow && (
                <span className="text-amber-500">
                  uwaga: heurystyki moga zwrocic 0 alertow (najnowsze tx)
                </span>
              )}
            </div>
          )}
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

        {experiment !== null ? (
          <ExperimentPanel
            rows={experiment}
            running={expRunning}
            progress={expProgress}
            hopsUsed={expHops}
            saveResult={expSaveResult}
            saveError={expSaveError}
          />
        ) : (
          <>
        {!result && !loading && !error && (
          <div className="rounded-lg border border-dashed border-neutral-700 bg-neutral-900 p-12 text-center">
            <div className="mb-3 text-4xl">🔍</div>
            <h3 className="mb-2 text-lg font-semibold">Wybierz case study lub wpisz adres</h3>
            <p className="text-sm text-neutral-400">
              Kliknij jeden z presetow u gory albo wklej dowolny adres Ethereum (0x...) i nacisnij
              Trace — albo kliknij{" "}
              <span className="font-medium text-emerald-300">Eksperyment 3×</span>, zeby od razu
              policzyc wszystkie 3 case&apos;y i dostac tabele porownawcza.
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
              <OverviewTab
                result={result}
                labelByAddress={labelByAddress}
                preset={currentPreset}
              />
            )}
            {activeTab === "graph" && (
              <GraphTab result={result} labelByAddress={labelByAddress} />
            )}
            {activeTab === "alerts" && <AlertsTab result={result} />}
            {activeTab === "transactions" && (
              <TransactionsTab result={result} labelByAddress={labelByAddress} />
            )}
            {activeTab === "labels" && <LabelsTab result={result} />}
            {activeTab === "metrics" && <MetricsTab result={result} />}
          </>
        )}
          </>
        )}
      </main>
    </div>
  );
}
