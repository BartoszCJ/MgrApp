// Typy TS odpowiadajace pydantic modelom z backendu (forensics/core/models.py).
// Trzymane recznie zsynchronizowane na razie - w przyszlosci mozna generowac z OpenAPI.

export type Transaction = {
  hash: string;
  block_number: number;
  timestamp: string; // ISO datetime
  from_address: string;
  to_address: string | null;
  value_wei: string;
  value_eth: number;
  gas_used: number;
  is_error: boolean;
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
  max_depth?: number;
  max_transactions?: number;
};

export type TraceResult = {
  root_address: string;
  transactions: Transaction[];
  labels: AddressLabel[];
  total_transactions: number;
  notes: string[];
};
