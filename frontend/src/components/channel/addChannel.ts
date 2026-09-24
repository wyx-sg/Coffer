// frontend/src/components/channel/addChannel.ts
//
// The pure half of AddChannelDialog: what the form holds, and how those values
// become either a validated draft or one message per field.
//
// It sits beside `editChannel.ts` for the same reason that file exists — the
// dialog is the markup, this is the rules — and it is what keeps the two
// halves of "add a channel" the same shape as the two halves of "edit" one.
//
// Nothing here reaches the network. `planChannel` (schema.ts) turns the values
// this validates into the resource config and the credential writes; the
// dialog is what sequences them.
import { addChannelFormSchema, type AddChannelFormValues } from "./schema";
import type { ChannelFieldErrors, ChannelSecretDraft } from "./AddChannelSecretFields";
import type { ChannelType } from "@/lib/api/channels";

/** Schema path (wire field name) → the input it is rendered under. */
const FIELD_OF_PATH: Record<string, keyof ChannelFieldErrors> = {
  name: "name",
  bot_token: "botToken",
  app_id: "appId",
  app_secret: "appSecret",
};

/** A blank credential draft — what the form opens on and resets to. */
export const EMPTY_SECRET_DRAFT: ChannelSecretDraft = {
  botToken: "",
  appId: "",
  appSecret: "",
};

/** Everything the add form holds that the schema has an opinion about. */
export interface AddChannelDraft {
  channelType: ChannelType;
  name: string;
  secrets: ChannelSecretDraft;
}

/** Valid values, or one message per field that has something wrong with it. */
export type AddChannelValidation =
  | { ok: true; values: AddChannelFormValues }
  | { ok: false; fieldErrors: ChannelFieldErrors };

/**
 * Validate the draft against the add-channel schema.
 *
 * `translate` is passed in rather than imported: the schema's issue messages
 * are i18n KEYS by contract (never zod's own English), and this module must
 * stay a pure function of its arguments so it can be read — and tested —
 * without a React tree around it.
 *
 * First issue per field wins, because the field shows one message and the
 * first is the one the schema considered most basic.
 */
export function validateAddChannel(
  draft: AddChannelDraft,
  translate: (key: string) => string,
): AddChannelValidation {
  const { channelType, name, secrets } = draft;
  const parsed = addChannelFormSchema.safeParse(
    channelType === "telegram"
      ? { channel_type: "telegram", name, bot_token: secrets.botToken }
      : {
          channel_type: "seatalk",
          name,
          app_id: secrets.appId,
          app_secret: secrets.appSecret,
        },
  );
  if (parsed.success) return { ok: true, values: parsed.data };

  const fieldErrors: ChannelFieldErrors = {};
  for (const issue of parsed.error.issues) {
    const field = FIELD_OF_PATH[String(issue.path[0])];
    if (field && !fieldErrors[field]) fieldErrors[field] = translate(issue.message);
  }
  return { ok: false, fieldErrors };
}
