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
// the shared `call` (.agents/frontend.md §4).

import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/channels";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ChannelType = Schemas["ChannelStatusOut"]["channel_type"];

/**
 * A SeaTalk channel's inbound state: the one outbound websocket connection it
 * receives every event on, and the last error behind it. Null for telegram.
 */
export type InboundInfo = Schemas["InboundInfoOut"];

/** Live state of a SeaTalk channel's websocket connection to the platform. */
export type WebSocketState = NonNullable<InboundInfo["websocket_state"]>;

export type ChannelStatus = Schemas["ChannelStatusOut"];

/** The paired owner of a channel (null while unpaired). */

/**
 * Something configured on the channel that the platform will not actually
 * honour. Empty is the healthy case; a diagnostic always names its fix.
 */

export type PairingCode = Schemas["PairingCodeOut"];

export type NotifyOut = Schemas["NotifyOut"];

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** Issue a single-use pairing code (replaces any previous pending code). */
export function issuePairingCode(uid: string): Promise<PairingCode> {
  return call<PairingCode>(`/channels/${enc(uid)}/pairing-code`, { method: "POST" });
}

/** Runtime, pairing, and inbound status of a channel. */
export function getChannelStatus(uid: string): Promise<ChannelStatus> {
  return call<ChannelStatus>(`/channels/${enc(uid)}/status`);
}

/** Push a text message to the channel's paired peer. */
export function notifyChannel(uid: string, text: string): Promise<NotifyOut> {
  return call<NotifyOut>(`/channels/${enc(uid)}/notify`, { method: "POST", body: { text } });
}
