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

/** One runtime answering at a loopback URL, with the models it serves. */
export type LocalRuntimeFound = Schemas["LocalRuntimeOut"];

export type DetectLocalOut = Schemas["DetectLocalOut"];

/** One model's price on a provider (USD per 1M tokens) and where it came
 *  from: `user` (You set), `provider` (its own API), `bundled` (the price list
 *  shipped with the release), `local` (costs nothing) — or `null`: unknown. */
export type ModelPrice = Schemas["ModelPriceOut"];
export type ModelPricesOut = Schemas["ModelPricesOut"];
/** The price list pricing reads now, and whether its daily refresh is on. */
export type PriceList = Schemas["PriceListOut"];
/** Its query key (kept here: queryKeys.ts is at its size limit). */
export const priceListKey = ["providers", "price-list"] as const;
/** A price the user sets on a curated model. */
export type CuratedPrice = NonNullable<ProviderModel["price"]>;

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
  // deliberate act with its own endpoint. The projection now names no
  // connection at all (it runs `coffer proxy token --agent-uid …`), which
  // leaves a rename as an ordinary label edit — `resourcesApi.rename`, the same PATCH every other
  // kind uses.

  remove: (uid: string) => call<void>(`/providers/${enc(uid)}`, { method: "DELETE" }),

  /** Put the providers in this order — fallback priority. Every uid once. */
  reorder: (uids: string[]) =>
    call<ProviderListOut>("/providers/order", { method: "PUT", body: { uids } }),

  /** The price list in use (bundled or refreshed) and its daily refresh. */
  priceList: () => call<PriceList>("/providers/price-list"),

  /** Turn the daily price-list refresh on or off on this machine. */
  setPriceRefresh: (refresh: boolean) =>
    call<PriceList>("/providers/price-list", { method: "PUT", body: { refresh } }),

  /** Each model's price on this provider, with its source. Read-only. */
  prices: (uid: string, models: string[]) =>
    call<ModelPricesOut>(`/providers/${enc(uid)}/prices`, { method: "POST", body: { models } }),

  /** Which local model runtime answers at a loopback URL — or, with `null`, at
   *  each runtime's default port. Read-only: nothing is pulled or loaded; a
   *  non-loopback URL is refused as 422. */
  detectLocal: (baseUrl: string | null) =>
    call<DetectLocalOut>("/providers/detect-local", {
      method: "POST",
      body: { base_url: baseUrl },
    }),

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
