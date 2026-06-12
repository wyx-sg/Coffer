// frontend/src/lib/api/channels.ts — typed fetch helpers for /api/v1/channels/*
// Hand-written wire types matching specs/009-channels/contracts/api.openapi.yaml
// and backend/coffer/surfaces/http/channel_routes.py (mirrors chat.ts: channel
// CRUD rides the generic /resources endpoints; these are the channel-specific
// operations — pairing, status, notify).

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ChannelType = "telegram" | "seatalk";

/** The paired owner of a channel (null while unpaired). */
export interface ChannelPeer {
  chat_id: string;
  display_name: string;
  paired_at: string;
  active_conversation_id: string | null;
}

/** SeaTalk callback listener endpoint — present for seatalk channels only. */
export interface CallbackInfo {
  port: number;
  path: string;
  listener_running: boolean;
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
}

export interface PairingCode {
  code: string;
  expires_at: string;
}

export interface NotifyOut {
  sent: boolean;
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
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
