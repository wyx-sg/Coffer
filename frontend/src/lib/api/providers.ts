// frontend/src/lib/api/providers.ts — typed fetch helpers for /api/v1/providers/*
// Hand-written wire types matching specs/011-provider-switching/contracts/api.openapi.yaml
// and backend/coffer/surfaces/http/provider_schemas.py.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type WireFormat = "anthropic" | "openai" | "ollama";
export type WireApi = "chat" | "responses";

/**
 * Chat agent_key → provider wire format (ADR-032 projection targets). Shared by
 * the chat ModelPicker and the agent Overview connection picker so both map an
 * agent to its compatible connections the same way. `ollama` is internal-only
 * (never projected to an agent), so it is not a value here.
 */
export const WIRE_BY_AGENT: Record<string, WireFormat> = {
  claude_code: "anthropic",
  codex: "openai",
};

/**
 * Curated built-in model ids per agent — the models reachable through the
 * agent's OWN login when no Coffer LLM connection overrides it. Chat offers
 * these alongside the active connection's model so a user can run on the
 * built-in model without configuring a connection (ADR-032 amendment D4). They
 * are passed verbatim to the agent's CLI: Claude Code resolves the
 * opus/sonnet/haiku aliases to the current model in each tier; Codex takes its
 * own model ids.
 */
export const BUILTIN_MODELS_BY_AGENT: Record<string, string[]> = {
  claude_code: ["opus", "sonnet", "haiku"],
  codex: ["gpt-5-codex", "gpt-5", "o3"],
};

export interface Provider {
  name: string;
  wire_format: WireFormat;
  base_url: string;
  /** Null for ollama (no key) and any connection created without a credential. */
  credential_ref: string | null;
  model: string;
  fast_model?: string | null;
  wire_api: WireApi;
  is_active: boolean;
  /** ≤1 globally — the connection Coffer's internal engine uses. */
  internal_default: boolean;
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

/** True only for anthropic/openai connections — ollama has no key. */
export function wireNeedsCredential(wire: WireFormat): boolean {
  return wire !== "ollama";
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

  /** Make this connection Coffer's internal-engine default (clears the flag on
   * all others). Returns the updated connection. */
  setInternalDefault: (name: string) =>
    call<Provider>("POST", `/providers/${name}/internal-default`),
};
