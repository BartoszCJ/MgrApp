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
};
