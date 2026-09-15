// frontend/src/lib/api/providers.ts — request helpers for /api/v1/providers/*
//
// The enums and the activate/deactivate answers are the provider-switching
// contract's generated schemas (`generated/provider-switching.ts`). The
// connection shapes themselves stay hand-written, because the contract lags
// the backend (`provider_schemas.py`): it omits `enabled` and `description` on
// the read side, `description` on create/patch, and `protocol` on patch, and
// marks `ProviderModel.modality` optional where the UI relies on it being set.
// Transport via the shared `call` (agents/frontend.md §4).

import { call } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/provider-switching";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// A connection's detected upstream protocol. `unknown` ⇒ the probe was
// inconclusive (the connection is offered to every agent; the user decides).
export type Protocol = Schemas["Protocol"];

// The agent types a connection may project into. Decoupled from `protocol`: the
// user routes any endpoint to any agent (e.g. an openai gateway → Claude Code).
// The set is not a connection FIELD any more — it is derived from the resource's
// framework per-agent scope (ADR per-agent-resource-scope), so it appears only on
// the read side (`Provider.compatible_agents`) and is changed through
// `PUT /resources/provider/{name}/scope` (see `lib/api/scope.ts`).
export type AgentType = Schemas["AgentType"];

/**
 * What KIND of model a curated entry names (provider-switching FR-029). One
 * endpoint serves more than chat — the same base URL and key answer for
 * embeddings, images, video and speech — so every picker asks for the kind it
 * needs instead of being handed every id: a chat dropdown takes `text`. This
 * says what the ENDPOINT serves; Coffer itself embeds nothing.
 */
export type Modality = Schemas["Modality"];

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
  /** READ-ONLY. The effective agents this connection projects into, derived
   * server-side from the resource's per-agent scope intersected with the agent
   * types Coffer knows; empty for a disabled or keyless (ollama) connection. The
   * Agent Overview picker and the chat ModelPicker filter on this. To CHANGE it,
   * write the scope (`scopeApi.put("provider", name, …)`) — there is no request
   * field for it. */
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
  /** Whole-value replace of the curated model set; `[]` clears the restriction. */
  models?: ProviderModel[] | null;
  description?: string | null;
}

export type ActivateOut = Schemas["ActivateOut"];

export type DeactivateOut = Schemas["DeactivateOut"];

/** True only for anthropic/openai/unknown connections — ollama has no key. */
export function wireNeedsCredential(wire: Protocol): boolean {
  return wire !== "ollama";
}

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const providersApi = {
  list: () => call<ProviderListOut>("/providers"),

  get: (name: string) => call<Provider>(`/providers/${name}`),

  create: (body: ProviderCreate) => call<Provider>("/providers", { method: "POST", body }),

  update: (name: string, body: ProviderPatch) =>
    call<Provider>(`/providers/${name}`, { method: "PATCH", body }),

  /** Rename a connection. Its own route rather than a PATCH field because a
   * name is a label rather than one of the connection's settings, and a name
   * already in use is a 409 rather than a merge. Nothing else moves: the vault
   * entry and the audit trail both hang off the resource's stable id. */
  rename: (name: string, newName: string) =>
    call<Provider>(`/providers/${name}/rename`, { method: "POST", body: { new_name: newName } }),

  remove: (name: string) => call<void>(`/providers/${name}`, { method: "DELETE" }),

  activate: (name: string) => call<ActivateOut>(`/providers/${name}/activate`, { method: "POST" }),

  /** Switch a wire's agent(s) back to their own built-in login: remove Coffer's
   * projection and clear the active connection. Idempotent. */
  useBuiltin: (wire: Protocol) =>
    call<DeactivateOut>(`/providers/use-builtin/${wire}`, { method: "POST" }),

  /** Make this connection Coffer's internal-engine default (clears the flag on
   * all others). Returns the updated connection. */
  setInternalDefault: (name: string) =>
    call<Provider>(`/providers/${name}/internal-default`, { method: "POST" }),
};
