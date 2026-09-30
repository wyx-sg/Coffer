// frontend/src/components/channel/ChannelReplaceSecretDialog.tsx
// Replace a channel's bot token (Telegram) or app secret (SeaTalk). The new
// value overwrites the credential the channel already points at, so pairing
// and settings are kept; then the adapter restarts on it. When the daemon
// holds the new value for approval instead, the channel keeps the old one
// until someone approves in the Coffer app, and nothing is restarted.
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

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
import { useReconnectChannel, useUpdateChannel } from "@/lib/hooks/useChannels";
import { planChannelEdit } from "./editChannel";

interface Props {
  channel: ResourceOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChannelReplaceSecretDialog({ channel, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const update = useUpdateChannel();
  const reconnect = useReconnectChannel(channel.uid);
  const [value, setValue] = useState("");
  const telegram = channel.config.channel_type === "telegram";
  const which = telegram ? "token" : "secret";

  const close = (o: boolean) => {
    if (!o) setValue("");
    onOpenChange(o);
  };

  const submit = () => {
    const agent = channel.config.default_agent;
    const plan = planChannelEdit({
      uid: channel.uid,
      name: channel.name,
      config: channel.config,
      values: {
        default_agent: typeof agent === "string" ? agent : "",
        ...(telegram ? { bot_token: value } : { app_secret: value }),
      },
    });
    update.mutate(plan, {
      onSuccess: ({ awaitingApproval }) => {
        if (!awaitingApproval && channel.enabled) reconnect.mutate({ enabled: true });
        close(false);
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(`channels.replace.${which}.title`)}</DialogTitle>
          <DialogDescription>{t(`channels.replace.${which}.body`)}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (value.trim()) submit();
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
        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={update.isPending || value.trim() === ""} onClick={submit}>
            {update.isPending ? t("common.saving") : t("channels.replace.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
