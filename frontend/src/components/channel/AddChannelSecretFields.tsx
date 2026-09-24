// frontend/src/components/channel/AddChannelSecretFields.tsx
// The platform-credential half of the add-channel form: which inputs each
// channel type asks for. Split out of AddChannelDialog so that file stays the
// FLOW (validate → plan → secrets-first register) rather than a wall of
// inputs. Values — and the per-field validation messages — are held by the
// dialog; this component only renders them, each message under its field.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import type { ChannelType } from "@/lib/api/channels";
import { FieldError, RequiredLabel } from "./RequiredLabel";

/** Every credential input the add form can show, across both channel types. */
export interface ChannelSecretDraft {
  botToken: string;
  appId: string;
  appSecret: string;
}

/** Translated validation messages, keyed by the input they belong under. */
export type ChannelFieldErrors = Partial<Record<keyof ChannelSecretDraft | "name", string>>;

export function AddChannelSecretFields({
  channelType,
  draft,
  errors,
  onChange,
}: {
  channelType: ChannelType;
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
      <div className="space-y-1 rounded-md border border-border bg-muted/30 p-3">
        <p className="text-xs text-muted-foreground">{t("channels.dialog.seatalkHint")}</p>
        <p className="text-xs text-muted-foreground">{t("channels.dialog.seatalkSdkNote")}</p>
        <p className="text-xs text-muted-foreground">{t("channels.dialog.seatalkPortalNote")}</p>
      </div>
    </>
  );
}
