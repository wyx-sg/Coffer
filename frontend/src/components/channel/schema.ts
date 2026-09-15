// frontend/src/components/channel/schema.ts
//
// Zod schema driving the add-channel form, plus the pure planning step that
// turns validated form values into the resource config + the list of
// credential-store writes. Field names mirror specs/channels/data-model.md:
// secrets never live in the config — only `*_ref` references do. Every issue
// message is an i18n KEY (`channels.dialog.errors.*`): the dialog renders
// `t(issue.message)` under the field the path names, never zod's own English.
//
// The CREATE path only. Edit planning moved to `editChannel.ts`, next to the
// apply that consumes it and to the test that was already named after it; the
// two paths shared this file without sharing anything but the two definitions
// below — `ChannelPlan`, the shape both produce, and `channelSecretRef`, which
// has to mint and re-find the same refs for both or a rotation would write to
// a ref nothing reads.
import { z } from "zod";

import type { ChannelDelivery, ChannelType } from "@/lib/api/channels";

/**
 * The agent a newly-created channel routes to by default: a chat provider KEY
 * (`claude_code`, underscore) — what the turn orchestrator resolves by — not
 * the `claude-code` resource name, which passes registration but fails at turn
 * time with UNKNOWN_AGENT. The backend validates it against the live provider
 * registry (the old "builtin" pseudo-agent is retired); the edit dialog re-binds.
 */
export const DEFAULT_AGENT = "claude_code";

const ERR = "channels.dialog.errors";
const channelNameSchema = z
  .string()
  .min(1, `${ERR}.name`)
  .max(64, `${ERR}.nameTooLong`)
  .regex(/^[a-zA-Z0-9_-]+$/, `${ERR}.nameFormat`);

/** The inbound transport a new SeaTalk channel is created on. */
export const DEFAULT_DELIVERY: ChannelDelivery = "webhook";

const addChannelFormUnion = z.discriminatedUnion("channel_type", [
  z.object({
    channel_type: z.literal("telegram"),
    name: channelNameSchema,
    bot_token: z.string().min(1, `${ERR}.botToken`),
  }),
  z.object({
    channel_type: z.literal("seatalk"),
    name: channelNameSchema,
    // Which transport SeaTalk delivers events on. Webhook is the default: it
    // is the method that works without the operator-supplied official SDK.
    delivery: z.enum(["webhook", "websocket"]).default(DEFAULT_DELIVERY),
    app_id: z.string().min(1, `${ERR}.appId`),
    app_secret: z.string().min(1, `${ERR}.appSecret`),
    // Required on webhook (it verifies every request's signature), forbidden on
    // websocket (the register handshake authenticates) — enforced below.
    signing_secret: z.string().optional(),
    // Optional: the tunnel's public base URL (https://host). The full SeaTalk
    // callback URL is composed from this on the channel detail page.
    public_base_url: z.string().optional(),
    // Optional: a cloudflared connector token. When set, Coffer runs the
    // named tunnel itself instead of the user running cloudflared by hand.
    tunnel_token: z.string().optional(),
  }),
]);

/**
 * The add-channel form. The cross-field rule sits on the union (a refinement
 * cannot live inside a discriminated-union member) and mirrors the backend's
 * `SeaTalkChannelConfig` validator field for field, so a submit never fails on
 * something the form could have told the user first.
 */
export const addChannelFormSchema = addChannelFormUnion.superRefine((values, ctx) => {
  if (values.channel_type !== "seatalk") return;
  const reject = (path: string, message: string) =>
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
  if (values.delivery === "webhook") {
    if (!values.signing_secret) reject("signing_secret", `${ERR}.signingSecret`);
    return;
  }
  // Websocket owns no signature, no public URL and no tunnel — a config field
  // that decides nothing would be a lie about the system.
  for (const field of ["signing_secret", "public_base_url", "tunnel_token"] as const) {
    if (values[field]?.trim()) reject(field, `${ERR}.websocketField`);
  }
});

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
 * effect runs, mirroring AddMcpServerDialog's planServer. `runsOn` is passed in
 * for the same reason the values are: this function may not go looking for it.
 *
 * Every created channel is BOUND, to the machine it was created from (spec
 * channels, "Where a channel runs"). A channel naming no machine means the
 * same thing on every machine that holds it, so no daemon can read it as "me"
 * and it runs nowhere — an unbound channel is a bot that never answers, which
 * is not a state a user should be able to fall into by filling in a form.
 */
export function planChannel(values: AddChannelFormValues, runsOn: string): ChannelPlan {
  if (values.channel_type === "telegram") {
    const ref = channelSecretRef(values.name, "bot-token");
    return {
      name: values.name,
      config: {
        channel_type: "telegram" satisfies ChannelType,
        bot_token_ref: ref,
        default_agent: DEFAULT_AGENT,
        runs_on: runsOn,
      },
      secrets: [{ ref, value: values.bot_token }],
    };
  }
  const appSecretRef = channelSecretRef(values.name, "app-secret");
  if (values.delivery === "websocket") {
    // No signing secret, no public URL, no tunnel: the bot dials out and the
    // register handshake (app id + app secret) authenticates the connection.
    return {
      name: values.name,
      config: {
        channel_type: "seatalk" satisfies ChannelType,
        delivery: "websocket" satisfies ChannelDelivery,
        app_id: values.app_id,
        app_secret_ref: appSecretRef,
        default_agent: DEFAULT_AGENT,
        runs_on: runsOn,
      },
      secrets: [{ ref: appSecretRef, value: values.app_secret }],
    };
  }
  const signingSecretRef = channelSecretRef(values.name, "signing-secret");
  const tunnelToken = values.tunnel_token?.trim();
  const tunnelTokenRef = channelSecretRef(values.name, "tunnel-token");
  return {
    name: values.name,
    config: {
      channel_type: "seatalk" satisfies ChannelType,
      delivery: "webhook" satisfies ChannelDelivery,
      app_id: values.app_id,
      app_secret_ref: appSecretRef,
      signing_secret_ref: signingSecretRef,
      default_agent: DEFAULT_AGENT,
      runs_on: runsOn,
      ...(values.public_base_url?.trim() ? { public_base_url: values.public_base_url.trim() } : {}),
      ...(tunnelToken ? { tunnel_token_ref: tunnelTokenRef } : {}),
    },
    secrets: [
      { ref: appSecretRef, value: values.app_secret },
      // The refinement above guarantees a signing secret on webhook delivery.
      { ref: signingSecretRef, value: values.signing_secret ?? "" },
      ...(tunnelToken ? [{ ref: tunnelTokenRef, value: tunnelToken }] : []),
    ],
  };
}
