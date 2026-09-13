// frontend/src/lib/api/channels.ts — typed fetch helpers for /api/v1/channels/*
// Hand-written wire types matching specs/channels/contracts/api.openapi.yaml
// and backend/coffer/surfaces/http/channel_routes.py (mirrors chat.ts: channel
// CRUD rides the generic /resources endpoints; these are the channel-specific
// operations — pairing, status, notify).

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ChannelType = "telegram" | "seatalk";

/**
 * How SeaTalk events reach Coffer. `webhook` needs a publicly reachable URL and
 * verifies a signing secret; `websocket` holds one outbound connection to the
 * platform and needs neither. A bot uses exactly one at a time.
 */
export type ChannelDelivery = "webhook" | "websocket";

/** Live state of a websocket-delivery channel's connection to SeaTalk. */
export type WebSocketState = "connecting" | "connected" | "kicked" | "sdk_missing" | "error";

/** The paired owner of a channel (null while unpaired). */
export interface ChannelPeer {
  chat_id: string;
  display_name: string;
  paired_at: string;
  active_conversation_id: string | null;
}

/**
 * SeaTalk inbound-delivery status — present for seatalk channels only. The
 * webhook-only fields below stay on the wire for both delivery methods, and
 * report their absent/false values on a websocket channel rather than
 * pretending a listener or a public URL exists.
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

/** Result of the public-callback reachability self-test. */
export interface CallbackTestResult {
  ok: boolean;
  detail: string;
}

/**
 * Something configured on the channel that the platform will not actually
 * honour. Empty is the healthy case; a diagnostic always names its fix.
 */
export interface ChannelDiagnostic {
  /** Stable identifier, so the UI can style or link the finding. */
  code: string;
  /** What is wrong and what to do about it. */
  message: string;
}

export interface ChannelStatus {
  name: string;
  channel_type: ChannelType;
  enabled: boolean;
  /** Whether the adapter task is currently live. */
  running: boolean;
  /** Whether an unexpired pairing code is outstanding. */
  pending_pairing?: boolean;
  peer: ChannelPeer | null;
  callback: CallbackInfo | null;
  /** Contradictions between the configuration and what the platform permits. */
  diagnostics?: ChannelDiagnostic[];
}

export interface PairingCode {
  code: string;
  expires_at: string;
  /**
   * A link carrying the code, so the owner pairs by opening it rather than
   * transcribing it. Empty when the platform has no such link.
   */
  pair_url?: string;
}

export interface NotifyOut {
  sent: boolean;
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function call<T>(method: "GET" | "POST" | "PUT", path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
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
// API functions
// ---------------------------------------------------------------------------

/** Issue a single-use pairing code (replaces any previous pending code). */
export function issuePairingCode(name: string): Promise<PairingCode> {
  return call<PairingCode>("POST", `/channels/${encodeURIComponent(name)}/pairing-code`);
}

/** Runtime, pairing, and callback status of a channel. */
export function getChannelStatus(name: string): Promise<ChannelStatus> {
  return call<ChannelStatus>("GET", `/channels/${encodeURIComponent(name)}/status`);
}

/** Push a text message to the channel's paired peer. */
export function notifyChannel(name: string, text: string): Promise<NotifyOut> {
  return call<NotifyOut>("POST", `/channels/${encodeURIComponent(name)}/notify`, { text });
}

/**
 * Probe the channel's public callback URL end to end (SeaTalk webhook delivery
 * only — a websocket channel has no public URL and the daemon rejects it).
 */
export function testChannelCallback(name: string): Promise<CallbackTestResult> {
  return call<CallbackTestResult>("POST", `/channels/${encodeURIComponent(name)}/callback-test`);
}
