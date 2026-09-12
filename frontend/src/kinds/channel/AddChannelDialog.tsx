// frontend/src/kinds/channel/AddChannelDialog.tsx
// Modal "Add channel" dialog. The user picks a type (Telegram / SeaTalk),
// names the channel, and pastes the platform secrets; registration plumbing
// (secrets-first write + rollback) lives in registerChannel.ts.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { ChannelType } from "@/lib/api/channels";
import { createChannel } from "./registerChannel";
import { AddChannelSecretFields, type ChannelSecretDraft } from "./AddChannelSecretFields";
import { addChannelFormSchema, planChannel, type ChannelPlan } from "./schema";

/** A blank credential draft — what the form opens on and resets to. */
const EMPTY_SECRET_DRAFT: ChannelSecretDraft = {
  botToken: "",
  appId: "",
  appSecret: "",
  signingSecret: "",
  publicBaseUrl: "",
  tunnelToken: "",
};

export function AddChannelDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [channelType, setChannelType] = useState<ChannelType>("telegram");
  const [name, setName] = useState("");
  const [secrets, setSecrets] = useState<ChannelSecretDraft>(EMPTY_SECRET_DRAFT);
  const patchSecrets = (patch: Partial<ChannelSecretDraft>) =>
    setSecrets((s) => ({ ...s, ...patch }));
  const [formError, setFormError] = useState<string | null>(null);

  const reset = () => {
    setChannelType("telegram");
    setName("");
    setSecrets(EMPTY_SECRET_DRAFT);
    setFormError(null);
  };

  const create = useMutation({
    mutationFn: (plan: ChannelPlan) => createChannel(plan),
    onSuccess: (createdName) => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
      toast.success(t("channels.dialog.created", { name: createdName }));
      reset();
      onOpenChange(false);
      navigate(`/channels/${createdName}`);
    },
    onError: (e) => {
      toast.error(translateApiError(t, e));
      setFormError(translateApiError(t, e));
    },
  });

  const submit = () => {
    setFormError(null);
    const parsed = addChannelFormSchema.safeParse(
      channelType === "telegram"
        ? { channel_type: "telegram", name, bot_token: secrets.botToken }
        : {
            channel_type: "seatalk",
            name,
            app_id: secrets.appId,
            app_secret: secrets.appSecret,
            signing_secret: secrets.signingSecret,
            public_base_url: secrets.publicBaseUrl,
            tunnel_token: secrets.tunnelToken,
          },
    );
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      setFormError(`${issue.path.join(".")}: ${issue.message}`);
      return;
    }
    create.mutate(planChannel(parsed.data));
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          create.reset();
          reset();
        }
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("channels.dialog.title")}</DialogTitle>
          <DialogDescription>{t("channels.dialog.subtitle")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="space-y-2">
            <Label>{t("channels.dialog.type")}</Label>
            <div className="flex gap-2" role="group" aria-label={t("channels.dialog.type")}>
              {(["telegram", "seatalk"] as const).map((ct) => (
                <Button
                  key={ct}
                  type="button"
                  size="sm"
                  variant={channelType === ct ? "default" : "outline"}
                  aria-pressed={channelType === ct}
                  onClick={() => setChannelType(ct)}
                >
                  {t(`channels.types.${ct}`)}
                </Button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="channel-name">{t("channels.dialog.name")}</Label>
            <Input
              id="channel-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. my-telegram"
            />
          </div>
          <AddChannelSecretFields
            channelType={channelType}
            draft={secrets}
            onChange={patchSecrets}
          />
          {formError ? (
            <p className="text-sm text-destructive" role="alert">
              {formError}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? t("common.saving") : t("channels.add")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
