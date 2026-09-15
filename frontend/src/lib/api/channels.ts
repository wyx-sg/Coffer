// frontend/src/lib/api/channels.ts — request helpers for /api/v1/channels/*
// (mirrors chat.ts: channel CRUD rides the generic /resources endpoints; these
// are the channel-specific operations — pairing, status, notify, callback test).
//
// Wire types are the channels contract's generated schemas
// (`specs/channels/contracts/api.openapi.yaml` → `generated/channels.ts`),
// re-exported under the names the hooks and pages already import. Transport is
// the shared `call` (agents/frontend.md §4).

import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/channels";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ChannelType = Schemas["ChannelStatusOut"]["channel_type"];

/**
 * How SeaTalk events reach Coffer. `webhook` needs a publicly reachable URL and
 * verifies a signing secret; `websocket` holds one outbound connection to the
 * platform and needs neither. A bot uses exactly one at a time.
 */
export type ChannelDelivery = Schemas["CallbackInfoOut"]["delivery"];

/** Live state of a websocket-delivery channel's connection to SeaTalk. */
export type WebSocketState = NonNullable<Schemas["CallbackInfoOut"]["websocket_state"]>;

/**
 * SeaTalk inbound-delivery status — present for seatalk channels only. The
 * webhook-only fields below stay on the wire for both delivery methods, and
 * report their absent/false values on a websocket channel rather than
 * pretending a listener or a public URL exists.
 *
 * Hand-written rather than the contract's `CallbackInfoOut`, which marks every
 * field past `listener_running` optional; the daemon always sends them and the
 * callback card narrows `websocket_state` on `!== null` alone.
 */
export interface CallbackInfo {
  /** Which inbound transport this channel uses. */
  delivery: ChannelDelivery;
  port: number;
  path: string;
  listener_running: boolean;
  /** The tunnel's public base URL the user recorded (null until set). */
  public_base_url: string | null;
  /** Full callback URL to register on SeaTalk (base + path); null until base set. */
  public_callback_url: string | null;
  /** Whether Coffer manages a cloudflared tunnel for this channel (token set). */
  tunnel_managed: boolean;
  /** Whether the managed cloudflared tunnel process is currently alive. */
  tunnel_running: boolean;
  /** Connection state of the websocket connector; null on webhook delivery. */
  websocket_state: WebSocketState | null;
  /** Last websocket error text; null when there is none. */
  websocket_error: string | null;
}

/** The contract's `ChannelStatusOut` with the hand-written `CallbackInfo` above. */
export type ChannelStatus = Omit<Schemas["ChannelStatusOut"], "callback"> & {
  callback: CallbackInfo | null;
};

/** The paired owner of a channel (null while unpaired). */
export type ChannelPeer = Schemas["ChannelPeerOut"];

/**
 * Something configured on the channel that the platform will not actually
 * honour. Empty is the healthy case; a diagnostic always names its fix.
 */
export type ChannelDiagnostic = Schemas["ChannelDiagnosticOut"];

export type PairingCode = Schemas["PairingCodeOut"];

export type NotifyOut = Schemas["NotifyOut"];

/**
 * Result of the public-callback reachability self-test. Hand-written: the
 * `callback-test` route is not in the channels contract.
 */
export interface CallbackTestResult {
  ok: boolean;
  detail: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** Issue a single-use pairing code (replaces any previous pending code). */
export function issuePairingCode(name: string): Promise<PairingCode> {
  return call<PairingCode>(`/channels/${enc(name)}/pairing-code`, { method: "POST" });
}

/** Runtime, pairing, and callback status of a channel. */
export function getChannelStatus(name: string): Promise<ChannelStatus> {
  return call<ChannelStatus>(`/channels/${enc(name)}/status`);
}

/** Push a text message to the channel's paired peer. */
export function notifyChannel(name: string, text: string): Promise<NotifyOut> {
  return call<NotifyOut>(`/channels/${enc(name)}/notify`, { method: "POST", body: { text } });
}

/**
 * Probe the channel's public callback URL end to end (SeaTalk webhook delivery
 * only — a websocket channel has no public URL and the daemon rejects it).
 */
export function testChannelCallback(name: string): Promise<CallbackTestResult> {
  return call<CallbackTestResult>(`/channels/${enc(name)}/callback-test`, { method: "POST" });
}
