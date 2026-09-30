// frontend/src/components/channel/editChannel.ts
// Apply plumbing for a channel's settings (the Settings tab's auto-save and
// the Replace secret dialog): rotated secrets are written to their
// existing secret refs FIRST (so the channel keeps working off the same
// refs), then the resource config is PATCHed (bound agent / SeaTalk app id /
// group gating / message batching / replies / /dir directories), with the
// title when it changed.
// Unlike registration there is nothing to roll back — overwriting a ref's
// value and PATCHing a live resource are both in-place updates.
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";

import {
  BURST_WAIT_DEFAULTS,
  storedBurstWait,
  storedNotifyAfter,
  storedShowSteps,
  type BurstWaitKey,
} from "./channelTurnSettings";
import type { ChannelEditPlan } from "./schema";

/** Write one secret. True when the daemon answered 202: the new value replaces
 *  one in use, so it is stored sealed and waits for approval in the Coffer app. */
async function writeSecret(ref: string, value: string): Promise<boolean> {
  const { data, error } = await getApiClient().POST("/secrets", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "secret write failed");
  return data?.approval !== undefined;
}

async function patchConfig(
  uid: string,
  config: Record<string, unknown>,
  title: string | null | undefined,
): Promise<void> {
  const { error } = await getApiClient().PATCH("/resources/{uid}", {
    params: { path: { uid } },
    // The title rides the same PATCH only when it moved.
    body: title === undefined ? { config } : { config, title },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "update failed");
}

/**
 * Rotate the changed secrets, then PATCH the config. Returns the uid it wrote
 * and the name to say it wrote — the caller needs both, and they are no longer
 * the same string — and whether a rotated secret now waits for approval in the
 * Coffer app. Secrets-first matches registration: a config that references a
 * ref whose value just changed must see the new value, never a stale one.
 */
export async function applyChannelEdit(
  plan: ChannelEditPlan,
): Promise<{ uid: string; name: string; awaitingApproval: boolean }> {
  let awaitingApproval = false;
  for (const s of plan.secrets) {
    if (await writeSecret(s.ref, s.value)) awaitingApproval = true;
  }
  await patchConfig(plan.uid, plan.config, plan.title);
  return { uid: plan.uid, name: plan.name, awaitingApproval };
}

/** Mutable edit-form inputs by channel type (secrets blank = "leave as-is"). */
export interface ChannelEditValues {
  /** The agent every new conversation on this channel binds to. */
  default_agent: string;
  /** New Telegram bot token; blank leaves the stored secret untouched. */
  bot_token?: string;
  /** SeaTalk app id (mutable config — not a secret). */
  app_id?: string;
  /** New SeaTalk app secret; blank leaves the stored secret untouched. */
  app_secret?: string;
  /** Answer in a group only when @mentioned / replied to. Undefined leaves the
   *  stored value alone — the form sends it only where the platform honours it
   *  (see honoursRequireMention). */
  require_mention?: boolean;
  /** Drop a group message that also @mentions another user. */
  ignore_other_mentions?: boolean;
  /** Quiet window (seconds) after a text message before the burst runs as one
   *  turn. Undefined leaves the stored value alone. */
  wait_after_text_seconds?: number;
  /** Quiet window (seconds) after a forwarded chat record or text-less files. */
  wait_after_forward_seconds?: number;
  /** List each step under the live status line while a turn runs. Undefined
   *  leaves the stored value alone. */
  show_steps?: boolean;
  /** A turn running at least this long (seconds) ends with a completion ping;
   *  0 turns it off. Undefined leaves the stored value alone. */
  notify_after_seconds?: number;
  /** The folders `/dir` may switch into, normalised (see normaliseDirectory).
   *  Undefined leaves the stored list alone. */
  directories?: string[];
  /** The folder new conversations start in (`default_agent_config.cwd`);
   *  `null` clears it. Undefined leaves the stored value alone. */
  default_directory?: string | null;
}

/** The most folders a channel may list (the backend's cap). */
export const DIRECTORIES_MAX = 32;

/** The channel's default working directory — where its new conversations
 *  start — or `null` when none is set (the agent's own applies). */
export function storedDefaultDirectory(config: Record<string, unknown>): string | null {
  const agentConfig = config.default_agent_config;
  if (agentConfig === null || typeof agentConfig !== "object") return null;
  const cwd = (agentConfig as Record<string, unknown>).cwd;
  return typeof cwd === "string" && cwd ? cwd : null;
}

/** One typed directory, normalised like the backend (trimmed, no trailing
 *  "/"), or `null` when it is not an absolute path. */
export function normaliseDirectory(text: string): string | null {
  const path = text.trim();
  if (!path.startsWith("/")) return null;
  return path.replace(/\/+$/, "") || "/";
}

/** The stored `/dir` allow-list, or empty when absent. */
export function storedDirectories(config: Record<string, unknown>): string[] {
  const v = config.directories;
  return Array.isArray(v) ? v.filter((d): d is string => typeof d === "string") : [];
}

/**
 * Whether this channel type delivers un-addressed group messages at all — the
 * only case where require-mention changes anything. SeaTalk sends the bot a
 * group message only when it @mentions the bot, so there the switch would gate
 * nothing.
 */
export function honoursRequireMention(channelType: unknown): boolean {
  return channelType === "telegram";
}

export interface ChannelEditInput {
  /** The channel's identity — what the PATCH is addressed to. */
  uid: string;
  /** Its label. Used only to name the channel in the toast — never to address
   *  it, and (since refs became opaque) never to mint one either. */
  name: string;
  /** The title to set (`null` clears it), or undefined to leave it alone. */
  title?: string | null;
  /** The channel's current resource config (the source of truth for refs). */
  config: Record<string, unknown>;
  values: ChannelEditValues;
}

/**
 * Plan an edit: rotate secrets into the channel's EXISTING refs (a rotation
 * never moves the ref, so the config is unchanged when only a secret changes)
 * and build the full config PATCH preserving every `*_ref` / unknown field
 * while applying the mutable changes (bound agent, SeaTalk app id, group
 * gating, message batching, replies, /dir directories).
 *
 * Pure (no network), mirroring planChannel: the config is fully assembled
 * before any side effect runs. A blank secret value writes no secret.
 */
export function planChannelEdit(input: ChannelEditInput): ChannelEditPlan {
  const { config, values } = input;
  const secrets: { ref: string; value: string }[] = [];
  const nextConfig: Record<string, unknown> = {
    ...config,
    default_agent: values.default_agent,
  };
  // A group switch is written only when it differs from what the config
  // already says (an absent key reads as the backend default), so an edit
  // that only rotates a secret PATCHes back exactly the config it read.
  if (
    values.require_mention !== undefined &&
    honoursRequireMention(config.channel_type) &&
    values.require_mention !== (config.require_mention ?? true)
  ) {
    nextConfig.require_mention = values.require_mention;
  }
  if (
    values.ignore_other_mentions !== undefined &&
    values.ignore_other_mentions !== (config.ignore_other_mentions ?? false)
  ) {
    nextConfig.ignore_other_mentions = values.ignore_other_mentions;
  }
  // The batching windows follow the same rule: written only when changed.
  for (const key of Object.keys(BURST_WAIT_DEFAULTS) as BurstWaitKey[]) {
    const next = values[key];
    if (next !== undefined && next !== storedBurstWait(config, key)) nextConfig[key] = next;
  }
  // And the reply settings.
  if (values.show_steps !== undefined && values.show_steps !== storedShowSteps(config)) {
    nextConfig.show_steps = values.show_steps;
  }
  if (
    values.notify_after_seconds !== undefined &&
    values.notify_after_seconds !== storedNotifyAfter(config)
  ) {
    nextConfig.notify_after_seconds = values.notify_after_seconds;
  }
  // So is the /dir allow-list (order matters: the chat lists it as given).
  if (
    values.directories !== undefined &&
    values.directories.join("\n") !== storedDirectories(config).join("\n")
  ) {
    nextConfig.directories = values.directories;
  }
  // The default directory lives in the default agent config, beside anything
  // else a CLI user put there.
  if (
    values.default_directory !== undefined &&
    values.default_directory !== storedDefaultDirectory(config)
  ) {
    const agentConfig =
      config.default_agent_config && typeof config.default_agent_config === "object"
        ? { ...(config.default_agent_config as Record<string, unknown>) }
        : {};
    if (values.default_directory === null) delete agentConfig.cwd;
    else agentConfig.cwd = values.default_directory;
    nextConfig.default_agent_config = Object.keys(agentConfig).length > 0 ? agentConfig : null;
  }

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

  const plan: ChannelEditPlan = { uid: input.uid, name: input.name, config: nextConfig, secrets };
  if (input.title !== undefined) plan.title = input.title;
  return plan;
}
