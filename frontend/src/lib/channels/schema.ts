// frontend/src/lib/channels/schema.ts
//
// Zod schema driving the add-channel form, plus the pure planning step that
// turns validated form values into the resource config + the list of
// secret-store writes. Field names mirror openspec/specs/channels/data-model.md:
// secrets never live in the config — only `*_ref` references do. Every issue
// message is an i18n KEY (`channels.dialog.errors.*`): the dialog renders
// `t(issue.message)` under the field the path names, never zod's own English.
//
// The CREATE path only. Edit planning moved to `editChannel.ts`, next to the
// apply that consumes it and to the test that was already named after it; the
// two paths shared this file without sharing anything but the two definitions
// below — `ChannelPlan`, the shape both produce, and `channelSecretRef`, which
// mints the address a secret is stored at. A ref is no longer re-findable from
// the channel's name, so a rotation must reuse the ref already in the config
// (see `editChannel.ts`) rather than mint a second one nothing reads.
import { z } from "zod";

import type { ChannelType } from "@/lib/api/channels";
import { mintSecretRef } from "@/lib/secretRef";
import { TITLE_MAX_LENGTH } from "@/lib/resourceTitle";

// There is no DEFAULT_AGENT constant any more. `default_agent` holds an agent
// RESOURCE UID, which is minted per vault, so no constant can name one — and
// the constant that used to sit here was the last place the frontend spelled a
// second vocabulary for an agent (a chat provider key, `claude_code`, beside
// the resource name `claude-code`). The add form now asks which registered
// agent the channel drives, exactly as the edit form always did, and sends
// that agent's uid.

const ERR = "channels.dialog.errors";
// A channel's name is any display name (spec channels "Name a channel by any
// display name"): it is stored as the resource's title, and the resource's own
// name — a label with the framework's character rules — is derived from it
// (`channelSlug`).
const channelNameSchema = z
  .string()
  .trim()
  .min(1, `${ERR}.name`)
  .max(TITLE_MAX_LENGTH, `${ERR}.nameTooLong`);

/**
 * The resource name derived from a display name: lowercase, every run of
 * characters the name rules refuse becomes one "-", trimmed of dashes, at most
 * 64 characters; "channel" when nothing is left. `taken` are the names already
 * used, and a clash gets "-2", "-3", … so the add never fails on a label the
 * person never typed.
 */
export function channelSlug(displayName: string, taken: Iterable<string> = []): string {
  const base =
    displayName
      .normalize("NFKD")
      .toLowerCase()
      .replace(/[^a-z0-9_.-]+/g, "-")
      .replace(/^[-.]+|[-.]+$/g, "")
      .slice(0, 60)
      .replace(/[-.]+$/, "") || "channel";
  const used = new Set(taken);
  if (!used.has(base)) return base;
  for (let n = 2; ; n += 1) {
    const candidate = `${base}-${n}`;
    if (!used.has(candidate)) return candidate;
  }
}

/**
 * The add-channel form. A SeaTalk channel carries its app id and app secret
 * and nothing else of SeaTalk's: it receives every event over one outbound
 * websocket connection, so there is no signature, public URL or tunnel to
 * configure.
 */
export const addChannelFormSchema = z.discriminatedUnion("channel_type", [
  z.object({
    channel_type: z.literal("telegram"),
    name: channelNameSchema,
    bot_token: z.string().min(1, `${ERR}.botToken`),
  }),
  z.object({
    channel_type: z.literal("seatalk"),
    name: channelNameSchema,
    app_id: z.string().min(1, `${ERR}.appId`),
    app_secret: z.string().min(1, `${ERR}.appSecret`),
  }),
]);

export type AddChannelFormValues = z.output<typeof addChannelFormSchema>;

export interface ChannelPlan {
  /** For a new channel, the display name the person typed: it becomes the
   *  title, and the resource name is derived from it at registration. */
  name: string;
  config: Record<string, unknown>;
  /** Secret-store writes to perform BEFORE registering the resource. */
  secrets: { ref: string; value: string }[];
}

/**
 * The same plan for a channel that already exists. It carries the `uid` the
 * PATCH is addressed to, beside the `name` the toast reads out — a created
 * channel has no uid yet, which is the whole difference between the two
 * shapes and the reason they are not one optional field.
 */
export interface ChannelEditPlan extends ChannelPlan {
  uid: string;
  /** The title to set (`null` clears it); absent when the title is unchanged. */
  title?: string | null;
}

/**
 * Turn validated form values into the resource config plus the secret-store
 * writes. Pure (no network) — the config is fully built before any side
 * effect runs, mirroring AddMcpServerDialog's planServer. `runsOn` is passed in
 * for the same reason the values are, and so is `defaultAgentUid`: this
 * function may not go looking for either.
 *
 * Every created channel is BOUND, to the machine it was created from (spec
 * channels, "Bind each channel to the one machine that runs it"). A channel naming no machine means the
 * same thing on every machine that holds it, so no daemon can read it as "me"
 * and it runs nowhere — an unbound channel is a bot that never answers, which
 * is not a state a user should be able to fall into by filling in a form.
 */
export function planChannel(
  values: AddChannelFormValues,
  runsOn: string,
  defaultAgentUid: string,
): ChannelPlan {
  if (values.channel_type === "telegram") {
    const ref = mintSecretRef();
    return {
      name: values.name,
      config: {
        channel_type: "telegram" satisfies ChannelType,
        bot_token_ref: ref,
        default_agent: defaultAgentUid,
        runs_on: runsOn,
      },
      secrets: [{ ref, value: values.bot_token }],
    };
  }
  // The bot dials out and the register handshake (app id + app secret)
  // authenticates the connection, so the app secret is the only secret.
  const appSecretRef = mintSecretRef();
  return {
    name: values.name,
    config: {
      channel_type: "seatalk" satisfies ChannelType,
      app_id: values.app_id,
      app_secret_ref: appSecretRef,
      default_agent: defaultAgentUid,
      runs_on: runsOn,
    },
    secrets: [{ ref: appSecretRef, value: values.app_secret }],
  };
}
