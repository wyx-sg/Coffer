// frontend/src/components/channel/editChannel.ts
// Apply plumbing for EditChannelDialog: rotated secrets are written to their
// existing credential refs FIRST (so the channel keeps working off the same
// refs), then the resource config is PATCHed (bound agent / SeaTalk app id).
// Unlike registration there is nothing to roll back — overwriting a ref's
// value and PATCHing a live resource are both in-place updates.
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";
import type { ChannelDelivery } from "@/lib/api/channels";

import { channelSecretRef, type ChannelPlan } from "./schema";

// The resource kind for channels. Inlined (not imported from useChannels) so
// this module stays free of a hook → editChannel → hook import cycle.
const CHANNEL_KIND = "channel";

async function writeSecret(ref: string, value: string): Promise<void> {
  const { error } = await getApiClient().POST("/credentials", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "credential write failed");
}

async function patchConfig(name: string, config: Record<string, unknown>): Promise<void> {
  const { error } = await getApiClient().PATCH("/resources/{kind}/{name}", {
    params: { path: { kind: CHANNEL_KIND, name } },
    body: { config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "update failed");
}

/**
 * Rotate the changed secrets, then PATCH the config. Returns the name.
 * Secrets-first matches registration: a config that references a ref whose
 * value just changed must see the new value, never a stale one.
 */
export async function applyChannelEdit(plan: ChannelPlan): Promise<string> {
  for (const s of plan.secrets) {
    await writeSecret(s.ref, s.value);
  }
  await patchConfig(plan.name, plan.config);
  return plan.name;
}

/** Mutable edit-form inputs by channel type (secrets blank = "leave as-is"). */
export interface ChannelEditValues {
  /** The agent every new conversation on this channel binds to. */
  default_agent: string;
  /** New Telegram bot token; blank leaves the stored credential untouched. */
  bot_token?: string;
  /** SeaTalk app id (mutable config — not a secret). */
  app_id?: string;
  /** SeaTalk inbound transport; undefined keeps whatever the config says. */
  delivery?: ChannelDelivery;
  /** New SeaTalk app secret; blank leaves the stored credential untouched. */
  app_secret?: string;
  /** New SeaTalk signing secret; blank leaves the stored credential untouched. */
  signing_secret?: string;
  /** SeaTalk public base URL (mutable config — not a secret); blank clears it. */
  public_base_url?: string;
  /** New cloudflared tunnel token; blank leaves the stored credential untouched. */
  tunnel_token?: string;
}

export interface ChannelEditInput {
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
export function planChannelEdit(input: ChannelEditInput): ChannelPlan {
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
    const delivery = values.delivery ?? (config.delivery === "websocket" ? "websocket" : "webhook");
    nextConfig.delivery = delivery;
    if (delivery === "websocket") {
      // The backend rejects a websocket config still carrying a webhook field,
      // so the switch drops them. Credential VALUES stay; only the refs go.
      delete nextConfig.signing_secret_ref;
      delete nextConfig.public_base_url;
      delete nextConfig.tunnel_token_ref;
      return { name: input.name, config: nextConfig, secrets };
    }
    if (values.public_base_url !== undefined) {
      // Blank clears the stored URL (backend normalizes "" → null).
      nextConfig.public_base_url = values.public_base_url.trim() || null;
    }
    if (values.signing_secret) {
      // Reuse the channel's ref, or mint the canonical one — the latter is the
      // switch back to webhook, where the reference was dropped.
      const ref =
        typeof config.signing_secret_ref === "string" && config.signing_secret_ref
          ? config.signing_secret_ref
          : channelSecretRef(input.name, "signing-secret");
      nextConfig.signing_secret_ref = ref;
      secrets.push({ ref, value: values.signing_secret });
    }
    if (values.tunnel_token?.trim()) {
      // Reuse the existing ref, or mint one the first time a token is set
      // (which also turns on Coffer-managed tunneling for this channel).
      const ref =
        typeof config.tunnel_token_ref === "string" && config.tunnel_token_ref
          ? config.tunnel_token_ref
          : channelSecretRef(input.name, "tunnel-token");
      nextConfig.tunnel_token_ref = ref;
      secrets.push({ ref, value: values.tunnel_token.trim() });
    }
  }

  return { name: input.name, config: nextConfig, secrets };
}
