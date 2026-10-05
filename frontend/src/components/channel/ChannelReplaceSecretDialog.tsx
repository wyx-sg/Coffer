// frontend/src/components/channel/ChannelReplaceSecretDialog.tsx
// Replace a channel's bot token (Telegram) or app secret (SeaTalk). The new
// value overwrites the secret the channel already points at, so pairing
// and settings are kept; the daemon notices the replaced secret and restarts
// the adapter on it by itself. When the daemon holds the new value for approval
// instead, the channel keeps the old one until someone approves in the Coffer
// app, and nothing is restarted until then.
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { SecretNameLink } from "@/components/secret/SecretNameLink";
import { SecretSourceSwitch, type SecretSource } from "@/components/secret/SecretSourceSwitch";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
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
  const id = useId();
  const update = useUpdateChannel();
  const [value, setValue] = useState("");
  const [source, setSource] = useState<SecretSource>("value");
  const [picked, setPicked] = useState("");
  const telegram = channel.config.channel_type === "telegram";
  const refKey = telegram ? "bot_token_ref" : "app_secret_ref";
  const currentRef = channel.config[refKey];
  const existing = source === "existing";
  const which = telegram ? "token" : "secret";
  const owner = useChannelStatus(channel.uid).data?.people[0]?.display_name ?? "";
  // The pasted value is checked against the platform as it lands, and against
  // the stored bot so the person is told whether the pairing will still hold.
  const pasted = value.trim();
  const check = useCredentialCheck(
    open && !existing && pasted.length >= (telegram ? 10 : 4)
      ? {
          platform: telegram ? "telegram" : "seatalk",
          channel_uid: channel.uid,
          ...(telegram ? { bot_token: pasted } : { app_secret: pasted }),
        }
      : null,
  );
  const rejected = check.state === "done" && !check.result.ok && check.result.reason === "rejected";

  const close = (o: boolean) => {
    if (!o) {
      setValue("");
      setSource("value");
      setPicked("");
    }
    onOpenChange(o);
  };

  const canSubmit = existing ? picked !== "" : value.trim() !== "" && !rejected;

  const submit = () => {
    const agent = channel.config.default_agent;
    const plan = planChannelEdit({
      uid: channel.uid,
      name: channel.name,
      config: channel.config,
      values: {
        default_agent: typeof agent === "string" ? agent : "",
        // Existing mode writes no value: the channel is re-pointed at the
        // picked secret and the old one stays untouched.
        ...(existing ? {} : telegram ? { bot_token: value } : { app_secret: value }),
      },
    });
    if (existing) plan.config = { ...plan.config, [refKey]: picked };
    update.mutate(plan, {
      onSuccess: () => close(false),
    });
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(`channels.replace.${which}.title`)}</DialogTitle>
          <DialogDescription>{t(`channels.replace.${which}.body`)}</DialogDescription>
        </DialogHeader>
        {typeof currentRef === "string" && currentRef ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-label text-text">{t("secretRef.current")}</span>
            <SecretNameLink
              secretRef={currentRef}
              className="text-xs"
              onNavigate={() => close(false)}
            />
          </div>
        ) : null}
        {typeof currentRef === "string" ? (
          <SecretSourceSwitch
            source={source}
            onSourceChange={setSource}
            currentRef={currentRef}
            picked={picked}
            onPick={setPicked}
            disabled={update.isPending}
          />
        ) : null}
        <form
          hidden={existing}
          className="space-y-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) submit();
          }}
        >
          <Label htmlFor={id} required>
            {t(`channels.replace.${which}.label`)}
          </Label>
          <PasswordInput
            id={id}
            value={value}
            autoComplete="off"
            onChange={(e) => setValue(e.target.value)}
          />
          <p className="text-xs text-text-muted">{t("channels.replace.hint")}</p>
        </form>
        {!existing ? (
          <ChannelCredentialNote
            id={`${id}-check`}
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
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={update.isPending || !canSubmit} onClick={submit}>
            {update.isPending
              ? t("common.saving")
              : existing
                ? t("secretRef.useSubmit")
                : t("channels.replace.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
