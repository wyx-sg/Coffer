// frontend/src/lib/api/providers.ts — request helpers for /api/v1/providers/*
//
// Every wire type is an alias of the provider-switching contract's generated
// schemas (`generated/provider-switching.ts`), generated from
// `provider_schemas.py`. Transport via the shared `call` (agents/frontend.md §4).

import { call, enc } from "@/lib/api/call";
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
// `PUT /resources/{uid}/scope` (see `lib/api/scope.ts`).
// Not exported: `@/lib/api/agents` is where the rest of the app takes this
// type from, and two names for one enum is how they drift. It is only
// spelled here because `compatible_agents` below is typed with it.
type AgentType = Schemas["AgentType"];

/**
 * What KIND of model a curated entry names (spec provider-switching "Store a
 * modality with each curated model"). One
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
export type ProviderModel = Schemas["ProviderModel"];

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

export type Provider = Schemas["ProviderOut"];

export type ProviderListOut = Schemas["ProviderListOut"];

export type ProviderCreate = Schemas["ProviderCreate"];

export type ProviderPatch = Schemas["ProviderPatch"];

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

  get: (uid: string) => call<Provider>(`/providers/${enc(uid)}`),

  create: (body: ProviderCreate) => call<Provider>("/providers", { method: "POST", body }),

  update: (uid: string, body: ProviderPatch) =>
    call<Provider>(`/providers/${enc(uid)}`, { method: "PATCH", body }),

  // There is no `rename` here. It was a route of this kind's own, and it
  // existed because the connection's name was its identity: the projection
  // Coffer wrote into an agent's config spelled it, so moving it had to be a
  // deliberate act with its own endpoint. The projection now spells the uid
  // (`coffer provider key --connection-uid …`), which leaves a rename as an
  // ordinary label edit — `resourcesApi.rename`, the same PATCH every other
  // kind uses.

  remove: (uid: string) => call<void>(`/providers/${enc(uid)}`, { method: "DELETE" }),

  activate: (uid: string) =>
    call<ActivateOut>(`/providers/${enc(uid)}/activate`, { method: "POST" }),

  /** Switch an agent type back to its own built-in login: remove Coffer's
   * projection and clear the connection active for it. Idempotent. */
  useBuiltin: (agentType: AgentType) =>
    call<DeactivateOut>(`/providers/use-builtin/${enc(agentType)}`, { method: "POST" }),

  /** Make this connection Coffer's internal-engine default (clears the flag on
   * all others). Returns the updated connection. */
  setInternalDefault: (uid: string) =>
    call<Provider>(`/providers/${enc(uid)}/internal-default`, { method: "POST" }),

  /** Make this connection the one Coffer transcribes speech on (clears the flag
   * on all others). The twin of `setInternalDefault`, never a substitute for
   * it: nothing falls back between the two. */
  setTranscribeDefault: (uid: string) =>
    call<Provider>(`/providers/${enc(uid)}/transcribe-default`, { method: "POST" }),
};
