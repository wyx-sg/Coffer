// frontend/src/kinds/channel/AddChannelSecretFields.tsx
// The platform-credential half of the add-channel form: which inputs each
// channel type asks for. Split out of AddChannelDialog so that file stays the
// FLOW (validate → plan → secrets-first register) rather than a wall of
// inputs. Values — and the per-field validation messages — are held by the
// dialog; this component only renders them, each message under its field.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import type { ChannelDelivery, ChannelType } from "@/lib/api/channels";
import { ChannelDeliveryField } from "./ChannelDeliveryField";
import { FieldError, RequiredLabel } from "./RequiredLabel";

/** Every credential input the add form can show, across both channel types. */
export interface ChannelSecretDraft {
  botToken: string;
  appId: string;
  appSecret: string;
  signingSecret: string;
  publicBaseUrl: string;
  tunnelToken: string;
}

/** Translated validation messages, keyed by the input they belong under. */
export type ChannelFieldErrors = Partial<Record<keyof ChannelSecretDraft | "name", string>>;

export function AddChannelSecretFields({
  channelType,
  delivery,
  onDeliveryChange,
  draft,
  errors,
  onChange,
}: {
  channelType: ChannelType;
  /** Which inbound transport a SeaTalk channel is being created on. */
  delivery: ChannelDelivery;
  onDeliveryChange: (delivery: ChannelDelivery) => void;
  draft: ChannelSecretDraft;
  errors: ChannelFieldErrors;
  onChange: (patch: Partial<ChannelSecretDraft>) => void;
}) {
  const { t } = useTranslation();

  if (channelType === "telegram") {
    return (
      <div className="space-y-2">
        <RequiredLabel htmlFor="channel-bot-token">{t("channels.dialog.botToken")}</RequiredLabel>
        <PasswordInput
          id="channel-bot-token"
          value={draft.botToken}
          onChange={(e) => onChange({ botToken: e.target.value })}
          autoComplete="off"
          aria-required
          aria-invalid={errors.botToken ? true : undefined}
          aria-describedby="channel-bot-token-error"
        />
        <FieldError id="channel-bot-token-error" message={errors.botToken} />
        <p className="text-xs text-muted-foreground">{t("channels.dialog.telegramHint")}</p>
      </div>
    );
  }

  return (
    <>
      <ChannelDeliveryField delivery={delivery} onChange={onDeliveryChange} />
      <div className="space-y-2">
        <RequiredLabel htmlFor="channel-app-id">{t("channels.dialog.appId")}</RequiredLabel>
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
      <div className="space-y-2">
        <RequiredLabel htmlFor="channel-app-secret">{t("channels.dialog.appSecret")}</RequiredLabel>
        <PasswordInput
          id="channel-app-secret"
          value={draft.appSecret}
          onChange={(e) => onChange({ appSecret: e.target.value })}
          autoComplete="off"
          aria-required
          aria-invalid={errors.appSecret ? true : undefined}
          aria-describedby="channel-app-secret-error"
        />
        <FieldError id="channel-app-secret-error" message={errors.appSecret} />
      </div>
      {/* Webhook-only: a websocket channel verifies no signature, publishes no
          URL and needs no tunnel, so these fields would decide nothing. */}
      {delivery === "webhook" ? (
        <>
          <div className="space-y-2">
            <RequiredLabel htmlFor="channel-signing-secret">
              {t("channels.dialog.signingSecret")}
            </RequiredLabel>
            <PasswordInput
              id="channel-signing-secret"
              value={draft.signingSecret}
              onChange={(e) => onChange({ signingSecret: e.target.value })}
              autoComplete="off"
              aria-required
              aria-invalid={errors.signingSecret ? true : undefined}
              aria-describedby="channel-signing-secret-error"
            />
            <FieldError id="channel-signing-secret-error" message={errors.signingSecret} />
            <p className="text-xs text-muted-foreground">{t("channels.dialog.seatalkHint")}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="channel-public-base-url">{t("channels.dialog.publicBaseUrl")}</Label>
            <Input
              id="channel-public-base-url"
              value={draft.publicBaseUrl}
              onChange={(e) => onChange({ publicBaseUrl: e.target.value })}
              placeholder={t("channels.dialog.publicBaseUrlPlaceholder")}
              autoComplete="off"
              inputMode="url"
              aria-invalid={errors.publicBaseUrl ? true : undefined}
              aria-describedby="channel-public-base-url-error"
            />
            <FieldError id="channel-public-base-url-error" message={errors.publicBaseUrl} />
            <p className="text-xs text-muted-foreground">
              {t("channels.dialog.publicBaseUrlHint")}
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="channel-tunnel-token">{t("channels.dialog.tunnelToken")}</Label>
            <PasswordInput
              id="channel-tunnel-token"
              value={draft.tunnelToken}
              onChange={(e) => onChange({ tunnelToken: e.target.value })}
              autoComplete="off"
              aria-invalid={errors.tunnelToken ? true : undefined}
              aria-describedby="channel-tunnel-token-error"
            />
            <FieldError id="channel-tunnel-token-error" message={errors.tunnelToken} />
            <p className="text-xs text-muted-foreground">{t("channels.dialog.tunnelTokenHint")}</p>
          </div>
        </>
      ) : null}
    </>
  );
}
