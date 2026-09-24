// frontend/src/components/channel/EditChannelSecretFields.tsx
// The credential half of the edit-channel form: SeaTalk's app id (config, not
// a secret) beside the rotation inputs, which are blank by default — a blank
// field rotates nothing and the stored value stays. Split out of
// EditChannelDialog so that file stays the flow (plan → secrets-first apply)
// rather than a wall of inputs.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";

/** Every input the edit form can show, across both channel types. */
export interface ChannelEditDraft {
  appId: string;
  botToken: string;
  appSecret: string;
}

export function EditChannelSecretFields({
  channelType,
  draft,
  onChange,
}: {
  channelType: string;
  draft: ChannelEditDraft;
  onChange: (patch: Partial<ChannelEditDraft>) => void;
}) {
  const { t } = useTranslation();

  return (
    <>
      {channelType === "seatalk" ? (
        <div className="space-y-2">
          <Label htmlFor="edit-channel-app-id">{t("channels.dialog.appId")}</Label>
          <Input
            id="edit-channel-app-id"
            value={draft.appId}
            onChange={(e) => onChange({ appId: e.target.value })}
            autoComplete="off"
          />
        </div>
      ) : null}

      {channelType === "telegram" ? (
        <div className="space-y-2">
          <Label htmlFor="edit-channel-bot-token">{t("channels.edit.newBotToken")}</Label>
          <PasswordInput
            id="edit-channel-bot-token"
            value={draft.botToken}
            onChange={(e) => onChange({ botToken: e.target.value })}
            autoComplete="off"
            placeholder={t("common.secretKeepBlank")}
          />
          <p className="text-xs text-muted-foreground">{t("channels.edit.rotateHint")}</p>
        </div>
      ) : (
        <>
          <div className="space-y-2">
            <Label htmlFor="edit-channel-app-secret">{t("channels.edit.newAppSecret")}</Label>
            <PasswordInput
              id="edit-channel-app-secret"
              value={draft.appSecret}
              onChange={(e) => onChange({ appSecret: e.target.value })}
              autoComplete="off"
              placeholder={t("common.secretKeepBlank")}
            />
          </div>
          <p className="text-xs text-muted-foreground">{t("channels.edit.rotateHint")}</p>
        </>
      )}
    </>
  );
}
