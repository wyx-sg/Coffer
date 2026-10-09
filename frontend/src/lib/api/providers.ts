// frontend/src/lib/api/providers.ts — request helpers for /api/v1/providers/*
//
// Every wire type is an alias of the provider-switching contract's generated
// schemas (`generated/provider-switching.ts`), generated from
// `provider_schemas.py`. Transport via the typed client (agents/frontend.md §4).

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/provider-switching";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// A connection's detected upstream protocol. `unknown` ⇒ the probe was
// inconclusive (the connection is offered to every agent; the user decides).
export type Protocol = Schemas["Protocol"];

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
 * agent to its compatible connections the same way. The retired `ollama`
 * protocol is never projected to an agent, so it is not a value here.
 */
export const WIRE_BY_AGENT: Record<string, Protocol> = {
  claude_code: "anthropic",
  codex: "openai",
};

export type Provider = Schemas["ProviderOut"];

export type ProviderCreate = Schemas["ProviderCreate"];

export type ProviderPatch = Schemas["ProviderPatch"];

/** One runtime answering at a loopback URL, with the models it serves. */
export type LocalRuntimeFound = Schemas["LocalRuntimeOut"];

export type DetectLocalOut = Schemas["DetectLocalOut"];

/** One model's price on a provider (USD per 1M tokens) and where it came
 *  from: `user` (You set), `provider` (its own API), `bundled` (the price list
 *  shipped with the release), `local` (costs nothing) — or `null`: unknown. */
export type ModelPrice = Schemas["ModelPriceOut"];
export type ModelWindow = Schemas["ModelWindowOut"];
/** The agent config changes deleting a provider makes (the review before Delete). */
export type ProviderDeletePreview = Schemas["ProviderDeletePreviewOut"];
/** A connection's kept health verdict (spec provider-switching "Know each
 *  connection's health without opening it"): reachable, key_rejected or
 *  unreachable, from a model-list check or an agent's real request. */
export type ProviderHealth = Schemas["ProviderHealthOut"];
/** The price list pricing reads now, and whether its daily refresh is on. */
export type PriceList = Schemas["PriceListOut"];
/** Its query key (kept here: queryKeys.ts is at its size limit). */
export const priceListKey = ["providers", "price-list"] as const;
/** A price the user sets on a curated model. */
export type CuratedPrice = NonNullable<ProviderModel["price"]>;

/** What an endpoint is asked with: a wire, URL and the stored key's ref — or an
 *  inline, not-yet-saved `secret_value` so a dialog can list before saving. */
export type ListModelsIn = Schemas["ListModelsIn"];
/** The same plus the one model the minimal probe request names. */
export type TestConnectionIn = Schemas["TestConnectionIn"];
/** What an endpoint reports it serves. Each id carries the modality Coffer
 *  INFERRED from its name (spec provider-switching "Offer only text models to
 *  chat pickers") — a pre-fill for the connection's model table, never a stored
 *  fact: once an entry is curated, the modality the user left on it is the truth. */
export type EndpointModelsOut = Schemas["ProviderModelsOut"];

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const providersApi = {
  list: () => unwrap(getApiClient().GET("/providers")),

  get: (uid: string) =>
    unwrap(getApiClient().GET("/providers/{uid}", { params: { path: { uid } } })),

  create: (body: ProviderCreate) => unwrap(getApiClient().POST("/providers", { body })),

  update: (uid: string, body: ProviderPatch) =>
    unwrap(getApiClient().PATCH("/providers/{uid}", { params: { path: { uid } }, body })),

  // There is no `rename` here. It was a route of this kind's own, and it
  // existed because the connection's name was its identity: the projection
  // Coffer wrote into an agent's config spelled it, so moving it had to be a
  // deliberate act with its own endpoint. The projection now names no
  // connection at all (it runs `coffer proxy token --agent-uid …`), which
  // leaves a rename as an ordinary label edit — `resourcesApi.rename`, the same PATCH every other
  // kind uses.

  /** What deleting the provider would change in the agents' own config files. Read-only. */
  deletePreview: (uid: string) =>
    unwrap(getApiClient().GET("/providers/{uid}/delete-preview", { params: { path: { uid } } })),

  remove: (uid: string) =>
    unwrapVoid(getApiClient().DELETE("/providers/{uid}", { params: { path: { uid } } })),

  /** The price list in use (bundled or refreshed) and its daily refresh. */
  priceList: () => unwrap(getApiClient().GET("/providers/price-list")),

  /** Turn the daily price-list refresh on or off on this machine. */
  setPriceRefresh: (refresh: boolean) =>
    unwrap(getApiClient().PUT("/providers/price-list", { body: { refresh } })),

  /** Each model's price on this provider, with its source. Read-only. */
  prices: (uid: string, models: string[]) =>
    unwrap(
      getApiClient().POST("/providers/{uid}/prices", {
        params: { path: { uid } },
        body: { models },
      }),
    ),

  /** Each model's context window on this provider, with its source. Read-only. */
  windows: (uid: string, models: string[]) =>
    unwrap(
      getApiClient().POST("/providers/{uid}/windows", {
        params: { path: { uid } },
        body: { models },
      }),
    ),

  /** Which local model runtime answers at a loopback URL — or, with `null`, at
   *  each runtime's default port. Read-only: nothing is pulled or loaded; a
   *  non-loopback URL is refused as 422. */
  detectLocal: (baseUrl: string | null) =>
    unwrap(getApiClient().POST("/providers/detect-local", { body: { base_url: baseUrl } })),

  /** Every connection's kept health verdict. Read-only; calls no endpoint. */
  health: () => unwrap(getApiClient().GET("/providers/health")),

  /** List this connection's models now and keep the verdict. */
  check: (uid: string) =>
    unwrap(getApiClient().POST("/providers/{uid}/check", { params: { path: { uid } } })),

  /** Make this connection the one Coffer transcribes speech on (clears the flag
   * on all others). */
  setTranscribeDefault: (uid: string) =>
    unwrap(
      getApiClient().POST("/providers/{uid}/transcribe-default", { params: { path: { uid } } }),
    ),
};

/** Introspect an endpoint without saving anything (`/models/*`). */
export const modelProbeApi = {
  /** List the models an endpoint reports. Empty list + message → the surface shows why. */
  list: (p: ListModelsIn) =>
    unwrap(
      getApiClient().POST("/models/list-models", {
        body: {
          provider: p.provider,
          base_url: p.base_url ?? null,
          secret_ref: p.secret_ref ?? null,
          secret_value: p.secret_value ?? null,
        },
      }),
    ),
  /** Probe a chat provider with a minimal request. */
  test: (p: TestConnectionIn, signal?: AbortSignal) =>
    unwrap(getApiClient().POST("/models/test-connection", { body: p, signal })),
};
