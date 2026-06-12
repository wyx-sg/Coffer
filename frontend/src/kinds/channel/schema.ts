// frontend/src/kinds/channel/schema.ts
//
// Zod schema driving the add-channel form, plus the pure planning step that
// turns validated form values into the resource config + the list of
// credential-store writes. Field names mirror specs/009-channels/data-model.md:
// secrets never live in the config — only `*_ref` references do.
import { z } from "zod";

import type { ChannelType } from "@/lib/api/channels";

/** Every channel conversation starts on the built-in agent for now. */
export const DEFAULT_AGENT = "builtin";

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
  secret: "bot-token" | "app-secret" | "signing-secret",
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
  return {
    name: values.name,
    config: {
      channel_type: "seatalk" satisfies ChannelType,
      app_id: values.app_id,
      app_secret_ref: appSecretRef,
      signing_secret_ref: signingSecretRef,
      default_agent: DEFAULT_AGENT,
    },
    secrets: [
      { ref: appSecretRef, value: values.app_secret },
      { ref: signingSecretRef, value: values.signing_secret },
    ],
  };
}
