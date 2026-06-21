// frontend/src/lib/api/providers.ts — typed fetch helpers for /api/v1/providers/*
// Hand-written wire types matching specs/011-provider-switching/contracts/api.openapi.yaml
// and backend/coffer/surfaces/http/provider_schemas.py.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type WireFormat = "anthropic" | "openai";
export type WireApi = "chat" | "responses";

export interface Provider {
  name: string;
  wire_format: WireFormat;
  base_url: string;
  credential_ref: string;
  model: string;
  fast_model?: string | null;
  wire_api: WireApi;
  is_active: boolean;
  enabled: boolean;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProviderListOut {
  providers: Provider[];
}

export interface ProviderCreate {
  name: string;
  wire_format: WireFormat;
  base_url: string;
  model: string;
  fast_model?: string | null;
  wire_api?: WireApi;
  credential_ref?: string | null;
  secret_value?: string | null;
  description?: string | null;
}

export interface ProviderPatch {
  base_url?: string | null;
  model?: string | null;
  fast_model?: string | null;
  wire_api?: WireApi | null;
  secret_value?: string | null;
  description?: string | null;
}

export interface ActivateOut {
  activated: string;
  wire_format: WireFormat;
  projected: string[];
  skipped: string[];
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function call<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 204) {
    return undefined as unknown as T;
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const err = data?.error;
    throw new ApiError(err?.code ?? "INTERNAL_ERROR", err?.message ?? `request failed: ${r.status}`);
  }
  return data as T;
}

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const providersApi = {
  list: () => call<ProviderListOut>("GET", "/providers"),

  create: (body: ProviderCreate) => call<Provider>("POST", "/providers", body),

  update: (name: string, body: ProviderPatch) => call<Provider>("PATCH", `/providers/${name}`, body),

  remove: (name: string) => call<void>("DELETE", `/providers/${name}`),

  activate: (name: string) => call<ActivateOut>("POST", `/providers/${name}/activate`),
};
