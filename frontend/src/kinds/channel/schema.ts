// frontend/src/kinds/channel/schema.ts
//
// Zod schema driving the add-channel form, plus the pure planning step that
// turns validated form values into the resource config + the list of
// credential-store writes. Field names mirror specs/009-channels/data-model.md:
// secrets never live in the config — only `*_ref` references do.
import { z } from "zod";

import type { ChannelType } from "@/lib/api/channels";

/**
 * The agent a newly-created channel routes to by default. This is a chat
 * provider KEY (`claude_code`, underscore) — the key the turn orchestrator
 * resolves an agent by — not the `claude-code` resource name. A hyphenated
 * value passes registration but fails at turn time with UNKNOWN_AGENT, leaving
 * the bot silently dead. The backend validates `default_agent` against the live
 * provider registry (ADR-024 retired the old "builtin" pseudo-agent). The owner
 * can re-bind it later via the edit dialog.
 */
export const DEFAULT_AGENT = "claude_code";

const channelNameSchema = z
  .string()
  .min(1, "name required")
  .max(64)
  .regex(/^[a-zA-Z0-9_-]+$/, "letters, digits, dash, underscore only");

export const addChannelFormSchema = z.discriminatedUnion("channel_type", [
  z.object({
    channel_type: z.literal("telegram"),
    name: channelNameSchema,
    bot_token: z.string().min(1, "bot token required"),
  }),
  z.object({
    channel_type: z.literal("seatalk"),
    name: channelNameSchema,
    app_id: z.string().min(1, "app id required"),
    app_secret: z.string().min(1, "app secret required"),
    signing_secret: z.string().min(1, "signing secret required"),
    // Optional: the tunnel's public base URL (https://host). The full SeaTalk
    // callback URL is composed from this on the channel detail page.
    public_base_url: z.string().optional(),
    // Optional: a cloudflared connector token. When set, Coffer runs the
    // named tunnel itself instead of the user running cloudflared by hand.
    tunnel_token: z.string().optional(),
  }),
]);

export type AddChannelFormValues = z.output<typeof addChannelFormSchema>;

export interface ChannelPlan {
  name: string;
  config: Record<string, unknown>;
  /** Credential-store writes to perform BEFORE registering the resource. */
  secrets: { ref: string; value: string }[];
}

/** Credential-store ref for one of a channel's secrets. */
export function channelSecretRef(
  name: string,
  secret: "bot-token" | "app-secret" | "signing-secret" | "tunnel-token",
): string {
  return `channel/${name}/${secret}`;
}

/**
 * Turn validated form values into the resource config plus the credential-store
 * writes. Pure (no network) — the config is fully built before any side
 * effect runs, mirroring AddMcpServerDialog's planServer.
 */
export function planChannel(values: AddChannelFormValues): ChannelPlan {
  if (values.channel_type === "telegram") {
    const ref = channelSecretRef(values.name, "bot-token");
    return {
      name: values.name,
      config: {
        channel_type: "telegram" satisfies ChannelType,
        bot_token_ref: ref,
        default_agent: DEFAULT_AGENT,
      },
      secrets: [{ ref, value: values.bot_token }],
    };
  }
  const appSecretRef = channelSecretRef(values.name, "app-secret");
  const signingSecretRef = channelSecretRef(values.name, "signing-secret");
  const tunnelToken = values.tunnel_token?.trim();
  const tunnelTokenRef = channelSecretRef(values.name, "tunnel-token");
  return {
    name: values.name,
    config: {
      channel_type: "seatalk" satisfies ChannelType,
      app_id: values.app_id,
      app_secret_ref: appSecretRef,
      signing_secret_ref: signingSecretRef,
      default_agent: DEFAULT_AGENT,
      ...(values.public_base_url?.trim()
        ? { public_base_url: values.public_base_url.trim() }
        : {}),
      ...(tunnelToken ? { tunnel_token_ref: tunnelTokenRef } : {}),
    },
    secrets: [
      { ref: appSecretRef, value: values.app_secret },
      { ref: signingSecretRef, value: values.signing_secret },
      ...(tunnelToken ? [{ ref: tunnelTokenRef, value: tunnelToken }] : []),
    ],
  };
}

// ---------------------------------------------------------------------------
// Edit planning
// ---------------------------------------------------------------------------

/** Mutable edit-form inputs by channel type (secrets blank = "leave as-is"). */
export interface ChannelEditValues {
  /** The agent every new conversation on this channel binds to. */
  default_agent: string;
  /** New Telegram bot token; blank leaves the stored credential untouched. */
  bot_token?: string;
  /** SeaTalk app id (mutable config — not a secret). */
  app_id?: string;
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
 * before any side effect runs. A blank secret value yields no credential
 * write — the existing value stays.
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
    if (values.public_base_url !== undefined) {
      // Blank clears the stored URL (backend normalizes "" → null).
      nextConfig.public_base_url = values.public_base_url.trim() || null;
    }
    const appSecretRef = config.app_secret_ref;
    const signingSecretRef = config.signing_secret_ref;
    if (values.app_secret && typeof appSecretRef === "string") {
      secrets.push({ ref: appSecretRef, value: values.app_secret });
    }
    if (values.signing_secret && typeof signingSecretRef === "string") {
      secrets.push({ ref: signingSecretRef, value: values.signing_secret });
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
