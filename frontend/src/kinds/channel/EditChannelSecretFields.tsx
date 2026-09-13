// frontend/src/kinds/channel/EditChannelSecretFields.tsx
// The credential half of the edit-channel form: the SeaTalk config fields that
// are not secrets (app id, public base URL) beside the rotation inputs, which
// are blank by default — a blank field rotates nothing and the stored value
// stays. Split out of EditChannelDialog so that file stays the flow (validate →
// plan → secrets-first apply) rather than a wall of inputs.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import type { ChannelDelivery } from "@/lib/api/channels";
import { ChannelDeliveryField } from "./ChannelDeliveryField";

/** Every input the edit form can show, across both channel types. */
export interface ChannelEditDraft {
  appId: string;
  publicBaseUrl: string;
  tunnelToken: string;
  botToken: string;
  appSecret: string;
  signingSecret: string;
}

export function EditChannelSecretFields({
  channelType,
  delivery,
  onDeliveryChange,
  draft,
  onChange,
}: {
  channelType: string;
  /** The SeaTalk channel's inbound transport (ignored for telegram). */
  delivery: ChannelDelivery;
  onDeliveryChange: (delivery: ChannelDelivery) => void;
  draft: ChannelEditDraft;
  onChange: (patch: Partial<ChannelEditDraft>) => void;
}) {
  const { t } = useTranslation();
  const webhook = delivery === "webhook";

  return (
    <>
      {channelType === "seatalk" ? (
        <>
          <ChannelDeliveryField delivery={delivery} onChange={onDeliveryChange} />
          <div className="space-y-2">
            <Label htmlFor="edit-channel-app-id">{t("channels.dialog.appId")}</Label>
            <Input
              id="edit-channel-app-id"
              value={draft.appId}
              onChange={(e) => onChange({ appId: e.target.value })}
              autoComplete="off"
            />
          </div>
        </>
      ) : null}

      {channelType === "seatalk" && webhook ? (
        <>
          <div className="space-y-2">
            <Label htmlFor="edit-channel-public-base-url">
              {t("channels.dialog.publicBaseUrl")}
            </Label>
            <Input
              id="edit-channel-public-base-url"
              value={draft.publicBaseUrl}
              onChange={(e) => onChange({ publicBaseUrl: e.target.value })}
              placeholder="https://xxx.trycloudflare.com"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              {t("channels.dialog.publicBaseUrlHint")}
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-channel-tunnel-token">{t("channels.dialog.tunnelToken")}</Label>
            <PasswordInput
              id="edit-channel-tunnel-token"
              value={draft.tunnelToken}
              onChange={(e) => onChange({ tunnelToken: e.target.value })}
              autoComplete="off"
              placeholder={t("channels.edit.rotatePlaceholder")}
            />
            <p className="text-xs text-muted-foreground">{t("channels.dialog.tunnelTokenHint")}</p>
          </div>
        </>
      ) : null}

      {channelType === "telegram" ? (
        <div className="space-y-2">
          <Label htmlFor="edit-channel-bot-token">{t("channels.edit.newBotToken")}</Label>
          <PasswordInput
            id="edit-channel-bot-token"
            value={draft.botToken}
            onChange={(e) => onChange({ botToken: e.target.value })}
            autoComplete="off"
            placeholder={t("channels.edit.rotatePlaceholder")}
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
              placeholder={t("channels.edit.rotatePlaceholder")}
            />
          </div>
          {/* Webhook-only: websocket delivery verifies no signature. */}
          {webhook ? (
            <div className="space-y-2">
              <Label htmlFor="edit-channel-signing-secret">
                {t("channels.edit.newSigningSecret")}
              </Label>
              <PasswordInput
                id="edit-channel-signing-secret"
                value={draft.signingSecret}
                onChange={(e) => onChange({ signingSecret: e.target.value })}
                autoComplete="off"
                placeholder={t("channels.edit.rotatePlaceholder")}
              />
            </div>
          ) : null}
          <p className="text-xs text-muted-foreground">{t("channels.edit.rotateHint")}</p>
        </>
      )}
    </>
  );
}
