// frontend/src/lib/api/providers.ts — typed fetch helpers for /api/v1/providers/*
// Hand-written wire types matching specs/provider-switching/contracts/api.openapi.yaml
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
export type AgentType = "claude_code" | "codex";

/**
 * What KIND of model a curated entry names (provider-switching FR-029). One
 * endpoint serves more than chat — the same base URL and key answer for
 * embeddings, images, video and speech — so every picker asks for the kind it
 * needs instead of being handed every id: a chat dropdown takes `text`, the
 * global embedding setting takes `embedding`.
 */
export type Modality = "text" | "embedding" | "image" | "video" | "audio";

/** The five values, in the order the connection editor lists them. */
export const MODALITIES: readonly Modality[] = [
  "text",
  "embedding",
  "image",
  "video",
  "audio",
] as const;

/**
 * One model on a connection: an opaque id plus its kind. The same shape is used
 * both ways — the entries a connection curates and the ids endpoint
 * introspection discovers (whose `modality` is Coffer's GUESS, a pre-fill the
 * user corrects) — so a discovered model round-trips into the curated set
 * without reshaping.
 */
export interface ProviderModel {
  id: string;
  modality: Modality;
}

/** The ids of `models`, optionally narrowed to ONE modality, order preserved. */
export function modelIds(models: ProviderModel[], modality?: Modality): string[] {
  return models.filter((m) => modality === undefined || m.modality === modality).map((m) => m.id);
}

/**
 * Chat agent_key → the protocol it speaks (provider-switching projection targets). Shared by
 * the chat ModelPicker and the agent Overview connection picker so both map an
 * agent to its compatible connections the same way. `ollama` is internal-only
 * (never projected to an agent), so it is not a value here.
 */
export const WIRE_BY_AGENT: Record<string, Protocol> = {
  claude_code: "anthropic",
  codex: "openai",
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
  /** The curated model set offered for this connection, each entry carrying its
   * modality. EMPTY = no restriction: every model the endpoint serves is
   * offered. Non-empty narrows every downstream picker to these entries OF THE
   * MODALITY it serves — a chat dropdown never sees an embedding model. */
  models: ProviderModel[];
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
  /** Curated model set (`{id, modality}` entries); omit or `[]` for "no
   * restriction". */
  models?: ProviderModel[] | null;
  description?: string | null;
}

export interface ProviderPatch {
  /** The wire the endpoint speaks; correctable when the probe guessed wrong. */
  protocol?: Protocol;
  base_url?: string | null;
  secret_value?: string | null;
  compatible_agents?: AgentType[] | null;
  /** Whole-value replace of the curated model set; `[]` clears the restriction. */
  models?: ProviderModel[] | null;
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
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
    );
  }
  return data as T;
}

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const providersApi = {
  list: () => call<ProviderListOut>("GET", "/providers"),

  get: (name: string) => call<Provider>("GET", `/providers/${name}`),

  create: (body: ProviderCreate) => call<Provider>("POST", "/providers", body),

  update: (name: string, body: ProviderPatch) =>
    call<Provider>("PATCH", `/providers/${name}`, body),

  /** Rename a connection. Its own route rather than a PATCH field because the
   * name is the connection's IDENTITY, not one of its settings: the daemon has
   * to repoint the vault entry, the audit trail and the projected agent config
   * in one operation, and a name already in use is a 409 rather than a merge. */
  rename: (name: string, newName: string) =>
    call<Provider>("POST", `/providers/${name}/rename`, { new_name: newName }),

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
