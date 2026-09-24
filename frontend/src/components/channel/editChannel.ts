// frontend/src/components/channel/editChannel.ts
// Apply plumbing for EditChannelDialog: rotated secrets are written to their
// existing credential refs FIRST (so the channel keeps working off the same
// refs), then the resource config is PATCHed (bound agent / SeaTalk app id).
// Unlike registration there is nothing to roll back — overwriting a ref's
// value and PATCHing a live resource are both in-place updates.
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";

import type { ChannelEditPlan } from "./schema";

async function writeSecret(ref: string, value: string): Promise<void> {
  const { error } = await getApiClient().POST("/credentials", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "credential write failed");
}

async function patchConfig(uid: string, config: Record<string, unknown>): Promise<void> {
  const { error } = await getApiClient().PATCH("/resources/{uid}", {
    params: { path: { uid } },
    body: { config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "update failed");
}

/**
 * Rotate the changed secrets, then PATCH the config. Returns the uid it wrote
 * and the name to say it wrote — the caller needs both, and they are no longer
 * the same string. Secrets-first matches registration: a config that references
 * a ref whose value just changed must see the new value, never a stale one.
 */
export async function applyChannelEdit(
  plan: ChannelEditPlan,
): Promise<{ uid: string; name: string }> {
  for (const s of plan.secrets) {
    await writeSecret(s.ref, s.value);
  }
  await patchConfig(plan.uid, plan.config);
  return { uid: plan.uid, name: plan.name };
}

/** Mutable edit-form inputs by channel type (secrets blank = "leave as-is"). */
interface ChannelEditValues {
  /** The agent every new conversation on this channel binds to. */
  default_agent: string;
  /** New Telegram bot token; blank leaves the stored credential untouched. */
  bot_token?: string;
  /** SeaTalk app id (mutable config — not a secret). */
  app_id?: string;
  /** New SeaTalk app secret; blank leaves the stored credential untouched. */
  app_secret?: string;
}

export interface ChannelEditInput {
  /** The channel's identity — what the PATCH is addressed to. */
  uid: string;
  /** Its label. Used only to name the channel in the toast — never to address
   *  it, and (since refs became opaque) never to mint one either. */
  name: string;
  /** The channel's current resource config (the source of truth for refs). */
  config: Record<string, unknown>;
  values: ChannelEditValues;
}

/**
 * Plan an edit: rotate secrets into the channel's EXISTING refs (a rotation
 * never moves the ref, so the config is unchanged when only a secret changes)
 * and build the full config PATCH preserving every `*_ref` / unknown field
 * while applying the mutable changes (bound agent, SeaTalk app id).
 *
 * Pure (no network), mirroring planChannel: the config is fully assembled
 * before any side effect runs. A blank secret value writes no credential.
 */
export function planChannelEdit(input: ChannelEditInput): ChannelEditPlan {
  const { config, values } = input;
  const secrets: { ref: string; value: string }[] = [];
  const nextConfig: Record<string, unknown> = {
    ...config,
    default_agent: values.default_agent,
  };

  if (config.channel_type === "telegram") {
    const ref = config.bot_token_ref;
    if (values.bot_token && typeof ref === "string") {
      secrets.push({ ref, value: values.bot_token });
    }
  } else if (config.channel_type === "seatalk") {
    if (values.app_id !== undefined) nextConfig.app_id = values.app_id;
    const appSecretRef = config.app_secret_ref;
    if (values.app_secret && typeof appSecretRef === "string") {
      secrets.push({ ref: appSecretRef, value: values.app_secret });
    }
  }

  return { uid: input.uid, name: input.name, config: nextConfig, secrets };
}
