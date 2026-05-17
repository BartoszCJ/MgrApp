"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { AddressLabel, TraceGraph } from "@/lib/types";

// ============================================================================
// Filtr: co pokazujemy
// ============================================================================

export type GraphFilter = "all" | "labeled" | "interesting";

function filterNodes(
  graph: TraceGraph,
  filter: GraphFilter,
  labelByAddress: Map<string, AddressLabel>,
): Set<string> {
  const keep = new Set<string>();
  // root zawsze
  keep.add(graph.root_address.toLowerCase());

  if (filter === "all") {
    graph.nodes.forEach((n) => keep.add(n.address.toLowerCase()));
    return keep;
  }

  // labeled = root + wszystkie z etykieta Arkham
  if (filter === "labeled") {
    for (const n of graph.nodes) {
      if (labelByAddress.has(n.address.toLowerCase()) || n.is_root || n.is_endpoint) {
        keep.add(n.address.toLowerCase());
      }
    }
  }

  // interesting = root + labeled + endpoints + top-N hop1 (z najwiekszym tx_count).
  // NIE rozszerzamy o sasiadow przez edges - to wciagalo wszystko z powrotem.
  if (filter === "interesting") {
    const HOP1_TOP_N = 12;
    const hop1Nodes = graph.nodes
      .filter((n) => n.depth === 1)
      .sort((a, b) => b.tx_count - a.tx_count)
      .slice(0, HOP1_TOP_N);

    for (const n of graph.nodes) {
      const addr = n.address.toLowerCase();
      if (n.is_root || n.is_endpoint || labelByAddress.has(addr)) {
        keep.add(addr);
      }
    }
    hop1Nodes.forEach((n) => keep.add(n.address.toLowerCase()));
  }

  return keep;
}

// ============================================================================
// Layout: warstwy poziome (hierarchiczny) + spread w pionie
// ============================================================================

function hierarchicalLayout(
  nodes: TraceGraph["nodes"],
  keepSet: Set<string>,
  labelByAddress: Map<string, AddressLabel>,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const byDepth = new Map<number, TraceGraph["nodes"]>();

  for (const n of nodes) {
    if (!keepSet.has(n.address.toLowerCase())) continue;
    if (!byDepth.has(n.depth)) byDepth.set(n.depth, []);
    byDepth.get(n.depth)!.push(n);
  }

  const COL_WIDTH = 420;
  const ROW_HEIGHT = 110;

  // Sortowanie per kolumna: labeled w srodku (najwazniejsze), unlabeled na zewnatrz
  // Priorytet: hacker > mixer > bridge > cex > inne_labeled > unlabeled
  const categoryPriority: Record<string, number> = {
    hacker: 1,
    mixer: 2,
    bridge: 3,
    cex: 4,
  };

  function priorityFor(n: TraceGraph["nodes"][number]): number {
    if (n.is_root) return 0;
    const label = labelByAddress.get(n.address.toLowerCase());
    if (label?.category) return categoryPriority[label.category] ?? 5;
    if (label) return 5;
    return 10;
  }

  for (const [depth, nodes] of byDepth) {
    // Sort: najwazniejsze na srodku - interleave priorities
    const sorted = [...nodes].sort((a, b) => priorityFor(a) - priorityFor(b));

    // Layout: najwazniejszy w srodku, reszta naprzemiennie gora/dol
    const ordered: typeof sorted = [];
    sorted.forEach((n, i) => {
      if (i % 2 === 0) ordered.push(n);
      else ordered.unshift(n);
    });

    const totalHeight = (ordered.length - 1) * ROW_HEIGHT;
    const startY = -totalHeight / 2;
    ordered.forEach((n, i) => {
      positions.set(n.address, {
        x: depth * COL_WIDTH,
        y: startY + i * ROW_HEIGHT,
      });
    });
  }

  return positions;
}

// ============================================================================
// Style per kategoria
// ============================================================================

const NODE_STYLE: Record<string, string> = {
  hacker: "border-red-500 bg-red-950 text-red-100",
  mixer: "border-purple-500 bg-purple-950 text-purple-100",
  bridge: "border-amber-500 bg-amber-950 text-amber-100",
  cex: "border-green-500 bg-green-950 text-green-100",
};

function nodeStyle(category: string | null | undefined, isRoot: boolean): string {
  if (isRoot) return "border-blue-400 bg-blue-900 text-blue-50 ring-2 ring-blue-400";
  if (!category) return "border-neutral-700 bg-neutral-900 text-neutral-300";
  return NODE_STYLE[category.toLowerCase()] ?? "border-neutral-700 bg-neutral-900 text-neutral-300";
}

const EDGE_COLOR: Record<string, string> = {
  ETH: "#60a5fa",
  WETH: "#3b82f6",
  USDC: "#22c55e",
  USDT: "#10b981",
  DAI: "#eab308",
  WBTC: "#f97316",
};

function edgeColor(token: string | null | undefined): string {
  if (!token) return EDGE_COLOR.ETH;
  return EDGE_COLOR[token.toUpperCase()] ?? "#a3a3a3";
}

// ============================================================================
// Custom node (z handles!)
// ============================================================================

type AddressNodeData = {
  label: string;
  category: string | null;
  isRoot: boolean;
  isEndpoint: boolean;
  txCount: number;
  address: string;
};

function AddressNode({ data }: { data: AddressNodeData }) {
  // Cztery handles: kazda strona moze byc i source, i target.
  // Edge wybiera odpowiednia pare bazujac na pozycji wzgledem siebie -
  // dzieki temu krawedzie nie zawijaja "w tyl" przy hop2 -> hop1 -> root.
  const handleClass = "!h-2 !w-2 !border-0 !bg-neutral-700 !opacity-0";
  return (
    <div
      className={`min-w-[170px] max-w-[230px] rounded-lg border-2 px-3 py-2 text-xs shadow-lg ${nodeStyle(
        data.category,
        data.isRoot,
      )}`}
    >
      <Handle id="left-target" type="target" position={Position.Left} className={handleClass} />
      <Handle id="left-source" type="source" position={Position.Left} className={handleClass} />
      <Handle id="right-target" type="target" position={Position.Right} className={handleClass} />
      <Handle id="right-source" type="source" position={Position.Right} className={handleClass} />

      <div className="truncate font-semibold leading-tight">{data.label}</div>
      <div className="mt-0.5 truncate font-mono text-[9px] opacity-60">
        {data.address.slice(0, 6)}…{data.address.slice(-4)}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1 text-[9px] opacity-80">
        {data.isRoot && (
          <span className="rounded bg-blue-700 px-1 font-bold text-blue-50">ROOT</span>
        )}
        {data.isEndpoint && (
          <span className="rounded bg-neutral-700 px-1 font-bold text-neutral-200">TERMINAL</span>
        )}
        {data.txCount > 0 && <span className="opacity-60">{data.txCount} tx</span>}
      </div>
    </div>
  );
}

const nodeTypes: NodeTypes = {
  address: AddressNode,
};

// ============================================================================
// Main component
// ============================================================================

export function TraceGraphView({
  graph,
  labelByAddress,
  filter = "interesting",
}: {
  graph: TraceGraph;
  labelByAddress: Map<string, AddressLabel>;
  filter?: GraphFilter;
}) {
  const { nodes, edges, kept } = useMemo(() => {
    const keepSet = filterNodes(graph, filter, labelByAddress);
    const positions = hierarchicalLayout(graph.nodes, keepSet, labelByAddress);

    const flowNodes: Node[] = graph.nodes
      .filter((gn) => keepSet.has(gn.address.toLowerCase()))
      .map((gn) => {
        const label = labelByAddress.get(gn.address.toLowerCase());
        const displayLabel =
          label?.label ?? label?.entity ?? `${gn.address.slice(0, 6)}…${gn.address.slice(-4)}`;
        const pos = positions.get(gn.address) ?? { x: 0, y: 0 };
        return {
          id: gn.address,
          type: "address",
          position: pos,
          data: {
            label: displayLabel,
            category: label?.category ?? null,
            isRoot: gn.is_root,
            isEndpoint: gn.is_endpoint,
            txCount: gn.tx_count,
            address: gn.address,
          },
        };
      });

    // Agregacja krawedzi miedzy ta sama para adresow
    const aggregated = new Map<
      string,
      { source: string; target: string; count: number; tokens: Map<string, number> }
    >();
    for (const e of graph.edges) {
      if (!keepSet.has(e.source) || !keepSet.has(e.target)) continue;
      const key = `${e.source}->${e.target}`;
      const bucket = aggregated.get(key) ?? {
        source: e.source,
        target: e.target,
        count: 0,
        tokens: new Map<string, number>(),
      };
      bucket.count += 1;
      const tk = e.token ?? "ETH";
      bucket.tokens.set(tk, (bucket.tokens.get(tk) ?? 0) + 1);
      aggregated.set(key, bucket);
    }

    const flowEdges: Edge[] = Array.from(aggregated.values()).map((agg, i) => {
      // Dominujacy token decyduje o kolorze
      const sortedTokens = Array.from(agg.tokens.entries()).sort((a, b) => b[1] - a[1]);
      const dominantToken = sortedTokens[0]?.[0] ?? "ETH";
      const label =
        agg.tokens.size === 1
          ? `${agg.count}× ${dominantToken}`
          : `${agg.count}× (${agg.tokens.size} tok)`;

      // Wybor handles po pozycji - source -> target wedlug osi X.
      const srcPos = positions.get(agg.source);
      const tgtPos = positions.get(agg.target);
      const goingRight = (srcPos?.x ?? 0) <= (tgtPos?.x ?? 0);
      const sourceHandle = goingRight ? "right-source" : "left-source";
      const targetHandle = goingRight ? "left-target" : "right-target";

      return {
        id: `e-${i}`,
        source: agg.source,
        target: agg.target,
        sourceHandle,
        targetHandle,
        label,
        labelStyle: { fill: "#d4d4d4", fontSize: 9, fontWeight: 600 },
        labelBgPadding: [4, 2],
        labelBgBorderRadius: 4,
        labelBgStyle: { fill: "#171717", fillOpacity: 0.85 },
        style: {
          stroke: edgeColor(dominantToken),
          strokeWidth: Math.min(1 + Math.log2(agg.count + 1), 4),
          opacity: 0.7,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: edgeColor(dominantToken),
          width: 14,
          height: 14,
        },
        type: "default",
      };
    });

    return {
      nodes: flowNodes,
      edges: flowEdges,
      kept: keepSet.size,
    };
  }, [graph, labelByAddress, filter]);

  return (
    <div className="relative h-[700px] w-full overflow-hidden rounded-lg border border-neutral-800 bg-neutral-950">
      <div className="absolute right-3 top-3 z-10 rounded bg-neutral-900/80 px-2 py-1 text-[10px] text-neutral-400 backdrop-blur">
        Pokazane: <span className="font-semibold text-neutral-200">{kept}</span> / {graph.nodes.length} węzłów
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.05}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#262626" gap={24} />
        <Controls className="!bg-neutral-900 !border-neutral-700" />
        <MiniMap
          className="!bg-neutral-900 !border-neutral-700"
          maskColor="rgba(10, 10, 10, 0.7)"
          nodeColor={(n) => {
            const d = n.data as AddressNodeData;
            if (d.isRoot) return "#3b82f6";
            if (d.category === "hacker") return "#dc2626";
            if (d.category === "mixer") return "#a855f7";
            if (d.category === "bridge") return "#f59e0b";
            if (d.category === "cex") return "#22c55e";
            return "#404040";
          }}
        />
      </ReactFlow>
    </div>
  );
}
