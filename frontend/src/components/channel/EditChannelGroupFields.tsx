// frontend/src/components/channel/EditChannelGroupFields.tsx
// The group half of a channel's Settings tab — spec channels "Configure when the
// bot answers in a group": require-mention and ignore-messages-that-@-someone-
// else, two plain config bools. Only the switches a platform honours are
// shown: SeaTalk delivers a group message to the bot only when it @mentions
// the bot, so require-mention has nothing to gate there and is Telegram-only.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow } from "@/components/settings/SettingsLayout";
import { Switch } from "@/components/ui/switch";
import { honoursRequireMention } from "@/lib/channels/editChannel";

/** The two group-gating switches, as the form holds them. */
export interface ChannelGroupDraft {
  requireMention: boolean;
  ignoreOtherMentions: boolean;
}

function SwitchRow({
  label,
  help,
  checked,
  onCheckedChange,
}: {
  label: string;
  help: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  const id = useId();
  const helpId = `${id}-help`;
  return (
    <SettingRow label={label} labelFor={id} description={help} descriptionId={helpId}>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-describedby={helpId}
      />
    </SettingRow>
  );
}

export function EditChannelGroupFields({
  channelType,
  draft,
  onChange,
}: {
  channelType: string;
  draft: ChannelGroupDraft;
  onChange: (patch: Partial<ChannelGroupDraft>) => void;
}) {
  const { t } = useTranslation();

  return (
    <>
      {honoursRequireMention(channelType) ? (
        <SwitchRow
          label={t("channels.edit.groups.requireMention")}
          help={t("channels.edit.groups.requireMentionHint")}
          checked={draft.requireMention}
          onCheckedChange={(requireMention) => onChange({ requireMention })}
        />
      ) : null}
      <SwitchRow
        label={t("channels.edit.groups.ignoreOtherMentions")}
        help={t("channels.edit.groups.ignoreOtherMentionsHint")}
        checked={draft.ignoreOtherMentions}
        onCheckedChange={(ignoreOtherMentions) => onChange({ ignoreOtherMentions })}
      />
    </>
  );
}
