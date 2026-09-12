// frontend/src/kinds/channel/AddChannelSecretFields.tsx
// The platform-credential half of the add-channel form: which inputs each
// channel type asks for. Split out of AddChannelDialog so that file stays the
// FLOW (validate → plan → secrets-first register) rather than a wall of
// inputs. Values are held by the dialog — this component only renders them.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import type { ChannelType } from "@/lib/api/channels";

/** Every credential input the add form can show, across both channel types. */
export interface ChannelSecretDraft {
  botToken: string;
  appId: string;
  appSecret: string;
  signingSecret: string;
  publicBaseUrl: string;
  tunnelToken: string;
}

export function AddChannelSecretFields({
  channelType,
  draft,
  onChange,
}: {
  channelType: ChannelType;
  draft: ChannelSecretDraft;
  onChange: (patch: Partial<ChannelSecretDraft>) => void;
}) {
  const { t } = useTranslation();

  if (channelType === "telegram") {
    return (
      <div className="space-y-2">
        <Label htmlFor="channel-bot-token">{t("channels.dialog.botToken")}</Label>
        <PasswordInput
          id="channel-bot-token"
          value={draft.botToken}
          onChange={(e) => onChange({ botToken: e.target.value })}
          autoComplete="off"
        />
        <p className="text-xs text-muted-foreground">{t("channels.dialog.telegramHint")}</p>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="channel-app-id">{t("channels.dialog.appId")}</Label>
        <Input
          id="channel-app-id"
          value={draft.appId}
          onChange={(e) => onChange({ appId: e.target.value })}
          autoComplete="off"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="channel-app-secret">{t("channels.dialog.appSecret")}</Label>
        <PasswordInput
          id="channel-app-secret"
          value={draft.appSecret}
          onChange={(e) => onChange({ appSecret: e.target.value })}
          autoComplete="off"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="channel-signing-secret">{t("channels.dialog.signingSecret")}</Label>
        <PasswordInput
          id="channel-signing-secret"
          value={draft.signingSecret}
          onChange={(e) => onChange({ signingSecret: e.target.value })}
          autoComplete="off"
        />
        <p className="text-xs text-muted-foreground">{t("channels.dialog.seatalkHint")}</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="channel-public-base-url">{t("channels.dialog.publicBaseUrl")}</Label>
        <Input
          id="channel-public-base-url"
          value={draft.publicBaseUrl}
          onChange={(e) => onChange({ publicBaseUrl: e.target.value })}
          placeholder="https://xxx.trycloudflare.com"
          autoComplete="off"
        />
        <p className="text-xs text-muted-foreground">{t("channels.dialog.publicBaseUrlHint")}</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="channel-tunnel-token">{t("channels.dialog.tunnelToken")}</Label>
        <PasswordInput
          id="channel-tunnel-token"
          value={draft.tunnelToken}
          onChange={(e) => onChange({ tunnelToken: e.target.value })}
          autoComplete="off"
        />
        <p className="text-xs text-muted-foreground">{t("channels.dialog.tunnelTokenHint")}</p>
      </div>
    </>
  );
}
