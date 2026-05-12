// Cienki klient do backendu FastAPI.

import type { TraceRequest, TraceResult } from "./types";

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
