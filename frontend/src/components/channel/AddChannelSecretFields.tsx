// frontend/src/components/channel/AddChannelSecretFields.tsx
// The platform-secret half of the add-channel form: which inputs each
// channel type asks for. Split out of AddChannelDialog so that file stays the
// FLOW (validate → plan → secrets-first register) rather than a wall of
// inputs. Values — and the per-field validation messages — are held by the
// dialog; this component only renders them, each message under its field.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SecretField } from "@/components/secret/SecretField";
import type { ChannelType } from "@/lib/api/channels";
import type { SecretFieldValue } from "@/lib/secretValue";
import { FieldError } from "./FieldError";

/** Every secret input the add form can show, across both channel types. */
export interface ChannelSecretDraft {
  /** The one secret field's value: a stored secret, or a pasted one written when the channel is added. */
  botToken: SecretFieldValue;
  appId: string;
  appSecret: SecretFieldValue;
}

/** Translated validation messages, keyed by the input they belong under. */
export type ChannelFieldErrors = Partial<Record<keyof ChannelSecretDraft | "name", string>>;

export function AddChannelSecretFields({
  channelType,
  channelName,
  draft,
  errors,
  onChange,
}: {
  channelType: ChannelType;
  /** What the person named the channel: a pasted secret is named after it. */
  channelName: string;
  draft: ChannelSecretDraft;
  errors: ChannelFieldErrors;
  onChange: (patch: Partial<ChannelSecretDraft>) => void;
}) {
  const { t } = useTranslation();

  if (channelType === "telegram") {
    return (
      <div className="space-y-1.5">
        <Label required htmlFor="channel-bot-token">
          {t("channels.dialog.botToken")}
        </Label>
        <SecretField
          id="channel-bot-token"
          value={draft.botToken}
          onChange={(botToken) => onChange({ botToken })}
          defaultName={t("channels.dialog.botTokenName", { name: channelName || "Telegram" })}
          aria-label={t("channels.dialog.botToken")}
          invalid={errors.botToken ? true : undefined}
          help={false}
        />
        <FieldError id="channel-bot-token-error" message={errors.botToken} />
        <p className="text-xs text-text-muted">{t("channels.dialog.telegramHint")}</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="space-y-1.5">
        <Label required htmlFor="channel-app-id">
          {t("channels.dialog.appId")}
        </Label>
        <Input
          id="channel-app-id"
          value={draft.appId}
          onChange={(e) => onChange({ appId: e.target.value })}
          autoComplete="off"
          aria-required
          aria-invalid={errors.appId ? true : undefined}
          aria-describedby="channel-app-id-error"
        />
        <FieldError id="channel-app-id-error" message={errors.appId} />
      </div>
      <div className="space-y-1.5">
        <Label required htmlFor="channel-app-secret">
          {t("channels.dialog.appSecret")}
        </Label>
        <SecretField
          id="channel-app-secret"
          value={draft.appSecret}
          onChange={(appSecret) => onChange({ appSecret })}
          defaultName={t("channels.dialog.appSecretName", { name: channelName || "SeaTalk" })}
          aria-label={t("channels.dialog.appSecret")}
          invalid={errors.appSecret ? true : undefined}
          help={false}
        />
        <FieldError id="channel-app-secret-error" message={errors.appSecret} />
      </div>
    </div>
  );
}
