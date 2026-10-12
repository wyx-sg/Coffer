// frontend/src/components/channel/ChannelReplaceSecretDialog.tsx
// Replace a channel's bot token (Telegram) or app secret (SeaTalk). The new
// value overwrites the secret the channel already points at, so pairing
// and settings are kept; the daemon notices the replaced secret and restarts
// the adapter on it by itself. When the daemon holds the new value for approval
// instead, the channel keeps the old one until someone approves in the Coffer
// app, and nothing is restarted until then.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ReplaceSecretDialog } from "@/components/secret/ReplaceSecretDialog";
import { EMPTY_DRAFT, type ReplaceDraft } from "@/components/secret/ReplaceSecretFields";
import type { ResourceOut } from "@/lib/api/resources";
import { useChannelStatus, useUpdateChannel } from "@/lib/hooks/useChannels";
import { useCredentialCheck } from "@/lib/hooks/useCredentialCheck";
import { planChannelEdit } from "@/lib/channels/editChannel";
import { ChannelCredentialNote } from "./ChannelCredentialNote";

interface Props {
  channel: ResourceOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChannelReplaceSecretDialog({ channel, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const update = useUpdateChannel();
  const [draft, setDraft] = useState<ReplaceDraft>(EMPTY_DRAFT);
  const telegram = channel.config.channel_type === "telegram";
  const refKey = telegram ? "bot_token_ref" : "app_secret_ref";
  const currentRef = channel.config[refKey];
  const which = telegram ? "token" : "secret";
  const owner = useChannelStatus(channel.uid).data?.people[0]?.display_name ?? "";
  // The pasted value is checked against the platform as it lands, and against
  // the stored bot so the person is told whether the pairing will still hold.
  const pasted = draft.source === "value" ? draft.value.trim() : "";
  const check = useCredentialCheck(
    open && pasted.length >= (telegram ? 10 : 4)
      ? {
          platform: telegram ? "telegram" : "seatalk",
          channel_uid: channel.uid,
          ...(telegram ? { bot_token: pasted } : { app_secret: pasted }),
        }
      : null,
  );
  const rejected = check.state === "done" && !check.result.ok && check.result.reason === "rejected";

  // A new value is written in place under the ref the channel cites; another
  // secret re-points the channel and leaves the old one untouched.
  const save = (values: { bot_token?: string; app_secret?: string }, picked?: string) => {
    const agent = channel.config.default_agent;
    const plan = planChannelEdit({
      uid: channel.uid,
      name: channel.name,
      config: channel.config,
      values: { default_agent: typeof agent === "string" ? agent : "", ...values },
    });
    if (picked) plan.config = { ...plan.config, [refKey]: picked };
    return update.mutateAsync(plan);
  };

  return (
    <ReplaceSecretDialog
      secretRef={open && typeof currentRef === "string" && currentRef ? currentRef : null}
      onClose={() => onOpenChange(false)}
      field={t(`channels.replace.${which}.label`)}
      description={t(`channels.replace.${which}.body`)}
      draft={draft}
      onDraftChange={setDraft}
      blocked={rejected}
      onReplaceValue={(value) => save(telegram ? { bot_token: value } : { app_secret: value })}
      onRebind={(ref) => save({}, ref)}
      check={
        <ChannelCredentialNote
          id={`channel-replace-check`}
          check={check}
          success={(r) => ({
            title: telegram
              ? r.bot_handle
                ? t("channels.replace.works", { handle: r.bot_handle })
                : t("channels.replace.worksPlain")
              : t("channels.replace.worksSeatalk"),
            body:
              r.same_bot === true
                ? owner
                  ? t("channels.replace.sameBot", { owner })
                  : t("channels.replace.sameBotPlain")
                : r.same_bot === false
                  ? t("channels.replace.differentBot")
                  : null,
          })}
        />
      }
    />
  );
}
