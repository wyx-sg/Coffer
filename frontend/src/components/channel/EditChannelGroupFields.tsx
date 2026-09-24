// frontend/src/components/channel/EditChannelGroupFields.tsx
// The group half of the edit-channel form — spec channels "Configure when the
// bot answers in a group": require-mention and ignore-messages-that-@-someone-
// else, two plain config bools. Only the switches a platform honours are
// shown: SeaTalk delivers a group message to the bot only when it @mentions
// the bot, so require-mention has nothing to gate there and is Telegram-only.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { honoursRequireMention } from "./editChannel";

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
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-0.5">
        <Label htmlFor={id}>{label}</Label>
        <p id={helpId} className="text-xs text-muted-foreground">
          {help}
        </p>
      </div>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-describedby={helpId}
      />
    </div>
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
    <fieldset className="space-y-3">
      <legend className="mb-2 text-sm font-medium">{t("channels.edit.groups.title")}</legend>
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
    </fieldset>
  );
}
