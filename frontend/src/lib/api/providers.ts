// frontend/src/lib/api/providers.ts — typed fetch helpers for /api/v1/providers/*
// Hand-written wire types matching specs/011-provider-switching/contracts/api.openapi.yaml
// and backend/coffer/surfaces/http/provider_schemas.py.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// A connection's detected upstream protocol. `unknown` ⇒ the probe was
// inconclusive (the connection is offered to every agent; the user decides).
export type Protocol = "anthropic" | "openai" | "ollama" | "unknown";

// The agent types a connection may project into. Decoupled from `protocol`: the
// user routes any endpoint to any agent (e.g. an openai gateway → Claude Code).
export type AgentType = "claude_code" | "codex" | "opencode" | "hermes";

/**
 * Chat agent_key → the protocol it speaks (ADR-032 projection targets). Shared by
 * the chat ModelPicker and the agent Overview connection picker so both map an
 * agent to its compatible connections the same way. `ollama` is internal-only
 * (never projected to an agent), so it is not a value here.
 */
export const WIRE_BY_AGENT: Record<string, Protocol> = {
  claude_code: "anthropic",
  codex: "openai",
  opencode: "openai",
  hermes: "openai",
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
  opencode: ["gpt-5", "gpt-5-codex", "claude-sonnet-4-5"],
  hermes: ["hermes-4-405b", "hermes-4-70b", "hermes-3-70b"],
};

export interface Provider {
  name: string;
  protocol: Protocol;
  base_url: string;
  /** Null for ollama (no key) and any connection created without a credential. */
  credential_ref: string | null;
  /** Effective (resolved) agents this connection projects into — the explicit
   * override or the wire default. The Agent Overview picker filters on this. */
  compatible_agents: AgentType[];
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
  protocol: Protocol;
  base_url: string;
  credential_ref?: string | null;
  secret_value?: string | null;
  /** Override the wire default for which agents the connection projects into. */
  compatible_agents?: AgentType[] | null;
  description?: string | null;
}

export interface ProviderPatch {
  base_url?: string | null;
  secret_value?: string | null;
  compatible_agents?: AgentType[] | null;
  description?: string | null;
}

export interface ActivateOut {
  activated: string;
  protocol: Protocol;
  projected: string[];
  skipped: string[];
}

export interface DeactivateOut {
  protocol: Protocol;
  deprojected: string[];
  previous: string | null;
}

/** True only for anthropic/openai/unknown connections — ollama has no key. */
export function wireNeedsCredential(wire: Protocol): boolean {
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

  /** Switch a wire's agent(s) back to their own built-in login: remove Coffer's
   * projection and clear the active connection. Idempotent. */
  useBuiltin: (wire: Protocol) => call<DeactivateOut>("POST", `/providers/use-builtin/${wire}`),

  /** Make this connection Coffer's internal-engine default (clears the flag on
   * all others). Returns the updated connection. */
  setInternalDefault: (name: string) =>
    call<Provider>("POST", `/providers/${name}/internal-default`),
};
