// Cienki klient do backendu FastAPI.

import type {
  CacheStatus,
  ExperimentSavePayload,
  ExperimentSaveResult,
  TraceRequest,
  TraceResult,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function trace(request: TraceRequest): Promise<TraceResult> {
  const response = await fetch(`${API_URL}/api/trace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(text || response.statusText, response.status);
  }

  return response.json();
}

export async function health(): Promise<{ status: string; version: string }> {
  const response = await fetch(`${API_URL}/`);
  if (!response.ok) throw new ApiError("API unavailable", response.status);
  return response.json();
}

export async function cacheStatus(): Promise<CacheStatus> {
  const response = await fetch(`${API_URL}/api/cache/status`);
  if (!response.ok) throw new ApiError("cache status unavailable", response.status);
  return response.json();
}

export async function clearCache(): Promise<{ deleted: number }> {
  const response = await fetch(`${API_URL}/api/cache`, { method: "DELETE" });
  if (!response.ok) throw new ApiError("cache clear failed", response.status);
  return response.json();
}

export async function saveExperiment(
  payload: ExperimentSavePayload,
): Promise<ExperimentSaveResult> {
  const response = await fetch(`${API_URL}/api/experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(text || response.statusText, response.status);
  }
  return response.json();
}
