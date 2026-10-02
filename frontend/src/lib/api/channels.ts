// frontend/src/lib/api/channels.ts — request helpers for /api/v1/channels/*
// (mirrors chat.ts: channel CRUD rides the generic /resources endpoints; these
// are the channel-specific operations — pairing, status, notify).
//
// Each takes the channel's `uid`, like every other route that addresses a
// resource. What a person reads on those surfaces is still `ResourceOut.name`.
//
// Wire types are the channels contract's generated schemas
// (`openspec/specs/channels/contracts/api.openapi.yaml` → `generated/channels.ts`),
// re-exported under the names the hooks and pages already import. Transport is
// the typed client through `unwrap` (.agents/frontend.md §4).

import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/channels";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ChannelType = Schemas["ChannelStatusOut"]["channel_type"];

export type ChannelStatus = Schemas["ChannelStatusOut"];

export type PairingCode = Schemas["PairingCodeOut"];

export type NotifyOut = Schemas["NotifyOut"];

export type RestartOut = Schemas["RestartOut"];

/** A channel's settings with every default filled in by the daemon — the typed
 *  reading of its configuration (`status.settings`), common fields included. */
export type ChannelSettings = NonNullable<Schemas["ChannelStatusOut"]["settings"]>;

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** Issue a single-use pairing code (replaces any previous pending code). */
export function issuePairingCode(uid: string): Promise<PairingCode> {
  return unwrap(getApiClient().POST("/channels/{uid}/pairing-code", { params: { path: { uid } } }));
}

/** Runtime, pairing, and inbound status of a channel. */
export function getChannelStatus(uid: string): Promise<ChannelStatus> {
  return unwrap(getApiClient().GET("/channels/{uid}/status", { params: { path: { uid } } }));
}

/** Stop the channel's adapter and start it again, reading its secret afresh. */
export function restartChannel(uid: string): Promise<RestartOut> {
  return unwrap(getApiClient().POST("/channels/{uid}/restart", { params: { path: { uid } } }));
}

/** Push a text message to the channel's paired peer. */
export function notifyChannel(uid: string, text: string): Promise<NotifyOut> {
  return unwrap(
    getApiClient().POST("/channels/{uid}/notify", {
      params: { path: { uid } },
      body: { text },
    }),
  );
}
