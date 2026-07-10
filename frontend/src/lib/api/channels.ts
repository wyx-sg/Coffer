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
  /** The tunnel's public base URL the user recorded (null until set). */
  public_base_url: string | null;
  /** Full callback URL to register on SeaTalk (base + path); null until base set. */
  public_callback_url: string | null;
  /** Whether Coffer manages a cloudflared tunnel for this channel (token set). */
  tunnel_managed: boolean;
  /** Whether the managed cloudflared tunnel process is currently alive. */
  tunnel_running: boolean;
}

/** Result of the public-callback reachability self-test. */
export interface CallbackTestResult {
  ok: boolean;
  detail: string;
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

/**
 * Machine x agent activation scope (ADR-045). Channels only ever use the
 * "machine" axis: a value is always "*" (bound to that one machine) — there
 * is no per-agent narrowing for channels, unlike mcp_server/skill/agent.
 * `{}` = dormant (runs nowhere); `{<machineId>: "*"}` = bound to that machine.
 * Supersedes `config.runs_on` (spec 009 amendment / ADR-045) — see
 * ChannelMachineCard.
 */
export type ChannelScopeValue = Record<string, "*">;

export interface ChannelScope {
  scope: ChannelScopeValue | null;
  axes: string[];
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

/** Probe the channel's public callback URL end to end (SeaTalk only). */
export function testChannelCallback(name: string): Promise<CallbackTestResult> {
  return call<CallbackTestResult>("POST", `/channels/${encodeURIComponent(name)}/callback-test`);
}

// ---------------------------------------------------------------------------
// Scope (ADR-045) — rides the generic /resources/{kind}/{name}/scope routes
// (Task 7), not /channels/*; kept here (rather than a generic reusable hook)
// until a framework-wide useResourceScope lands and can absorb this.
// ---------------------------------------------------------------------------

/** Current machine-activation scope for a channel + which axes it supports. */
export function getChannelScope(name: string): Promise<ChannelScope> {
  return call<ChannelScope>("GET", `/resources/channel/${encodeURIComponent(name)}/scope`);
}

/** Set (or clear, with `{}`) which single machine the channel runs on. */
export function updateChannelScope(
  name: string,
  scope: ChannelScopeValue,
): Promise<{ scope: ChannelScopeValue | null }> {
  return call<{ scope: ChannelScopeValue | null }>(
    "PUT",
    `/resources/channel/${encodeURIComponent(name)}/scope`,
    { scope },
  );
}
