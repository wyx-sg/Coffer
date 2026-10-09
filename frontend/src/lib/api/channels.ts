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

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
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

export type CredentialCheck = Schemas["CredentialCheckOut"];

export type CredentialCheckRequest = Schemas["ValidateCredentialsIn"];

/** A channel's settings with every default filled in by the daemon — the typed
 *  reading of its configuration (`status.settings`), common fields included. */
export type ChannelSettings = NonNullable<Schemas["ChannelStatusOut"]["settings"]>;

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export type ChannelPerson = Schemas["ChannelPersonOut"];

/** Issue a single-use pairing code (replaces any previous pending code). Whoever
 *  sends it is added as an owner; with `replaces` (a paired person's `sender_id`)
 *  they take that person's place instead. */
export function issuePairingCode(uid: string, replaces?: string): Promise<PairingCode> {
  return unwrap(
    getApiClient().POST("/channels/{uid}/pairing-code", {
      params: { path: { uid } },
      ...(replaces ? { body: { replaces } } : {}),
    }),
  );
}

/** Withdraw the channel's outstanding pairing code. */
export async function cancelPairingCode(uid: string): Promise<void> {
  await unwrapVoid(
    getApiClient().DELETE("/channels/{uid}/pairing-code", { params: { path: { uid } } }),
  );
}

/** Un-pair one person (their direct chat and the groups they brought the bot into). */
export async function removeChannelPerson(uid: string, senderId: string): Promise<void> {
  await unwrapVoid(
    getApiClient().DELETE("/channels/{uid}/people/{sender_id}", {
      params: { path: { uid, sender_id: senderId } },
    }),
  );
}

/** A paired person's picture on the platform as a `data:` URL, or `null` when
 *  there is none to show — the list shows their initials then. The picture is
 *  cosmetic, so a failed request is `null` too rather than an error. */
export async function getChannelPersonAvatar(
  uid: string,
  senderId: string,
): Promise<string | null> {
  const { data, response } = await getApiClient().GET("/channels/{uid}/people/{sender_id}/avatar", {
    params: { path: { uid, sender_id: senderId } },
    parseAs: "blob",
  });
  if (response.status !== 200 || !(data instanceof Blob) || data.size === 0) return null;
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : null);
    reader.onerror = () => resolve(null);
    reader.readAsDataURL(data);
  });
}

/** Runtime, pairing, and inbound status of a channel. */
export function getChannelStatus(uid: string): Promise<ChannelStatus> {
  return unwrap(getApiClient().GET("/channels/{uid}/status", { params: { path: { uid } } }));
}

/** Stop the channel's adapter and start it again, reading its secret afresh. */
export function restartChannel(uid: string): Promise<RestartOut> {
  return unwrap(getApiClient().POST("/channels/{uid}/restart", { params: { path: { uid } } }));
}

/** Push a text message to the channel's first paired owner. */
export function notifyChannel(uid: string, text: string): Promise<NotifyOut> {
  return unwrap(
    getApiClient().POST("/channels/{uid}/notify", {
      params: { path: { uid } },
      body: { text },
    }),
  );
}

/** Check credentials against the platform without storing them. A refusal is an
 *  ordinary answer (`ok: false` with a `reason`), not a thrown error. */
export function validateCredentials(body: CredentialCheckRequest): Promise<CredentialCheck> {
  return unwrap(getApiClient().POST("/channels/validate-credentials", { body }));
}
