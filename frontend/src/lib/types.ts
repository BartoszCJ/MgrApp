// Typy TS odpowiadajace pydantic modelom z backendu (forensics/core/models.py).
// Trzymane recznie zsynchronizowane na razie - w przyszlosci mozna generowac z OpenAPI.

export type Transaction = {
  hash: string;
  block_number: number;
  timestamp: string; // ISO datetime
  from_address: string;
  to_address: string | null;
  value_wei: string;
  value_eth: number; // dla ERC-20 to wartosc w jednostkach tokenu
  gas_used: number;
  is_error: boolean;
  // Token transfer (null dla normalnych ETH tx)
  token_symbol: string | null;
  token_name: string | null;
  token_contract: string | null;
  token_decimals: number | null;
};

export type AddressLabel = {
  address: string;
  label: string | null;
  entity: string | null;
  category: string | null;
  source: string | null;
};

export type TraceRequest = {
  address: string;
  hops?: number;
  max_transactions?: number;
  max_per_hop?: number;
  start_block?: number | null;
  end_block?: number | null;
  case_name?: string | null;
  refresh?: boolean; // pomin cache i pobierz na zywo
};

export type ProviderCache = { hit: number; miss: number };

export type CacheInfo = {
  mode?: string; // 'normal' | 'refresh'
  providers?: Record<string, ProviderCache>;
};

export type MetricsReport = {
  case_name: string;
  address_recall: number; // 0-1
  heuristic_precision: number; // 0-1
  heuristic_recall: number; // 0-1
  cex_coverage: number; // 0-1
  latency_seconds: number;
  breakdown: {
    addresses_found?: number;
    addresses_expected?: number;
    addresses_in_trace?: number;
    heuristics_hit?: string[];
    heuristics_expected?: string[];
    heuristics_false_positives?: string[];
    heuristics_missing?: string[];
    cex_destination_addresses_found?: number;
    cex_destination_addresses_expected?: number;
    cex_destination_exchanges_found?: string[];
    cex_destination_exchanges_expected?: string[];
    cex_alert_exchanges_detected_raw?: string[];
    [k: string]: unknown;
  };
  notes: string[];
};

export type Alert = {
  type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  related_addresses: string[];
  related_tx_hashes: string[];
  metadata: Record<string, unknown>;
};

export type GraphNode = {
  address: string;
  depth: number;
  tx_count: number;
  is_endpoint: boolean;
  is_root: boolean;
};

export type GraphEdge = {
  source: string;
  target: string;
  tx_hash: string;
  value: number;
  token: string | null;
  block: number;
};

export type TraceGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  root_address: string;
  hops: number;
  fetched_addresses: number;
};

export type TraceResult = {
  root_address: string;
  transactions: Transaction[];
  labels: AddressLabel[];
  alerts: Alert[];
  graph: TraceGraph | null;
  total_transactions: number;
  notes: string[];
  metrics: MetricsReport | null;
  cache: CacheInfo;
};

// ---- Cache zarzadzanie + zapis eksperymentu ----

export type CacheStatus = {
  cache_version: number;
  dir: string;
  total_files: number;
  total_bytes: number;
  providers: Record<string, number>;
};

export type ExperimentCasePayload = {
  case: string;
  address: string;
  hops: number;
  start_block: number | null;
  end_block: number | null;
  nodes: number;
  edges: number;
  alerts: number;
  labels: number;
  metrics: MetricsReport | null;
  cache: CacheInfo;
  error: string | null;
};

export type ExperimentSavePayload = {
  cache_mode: string;
  cases: ExperimentCasePayload[];
};

export type ExperimentSaveResult = {
  timestamp: string;
  commit_hash: string | null;
  files: string[];
  saved_dir: string;
};
