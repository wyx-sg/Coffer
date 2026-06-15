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
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { ChannelType } from "@/lib/api/channels";
import { createChannel } from "./registerChannel";
import { addChannelFormSchema, planChannel, type ChannelPlan } from "./schema";

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
  const [botToken, setBotToken] = useState("");
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [signingSecret, setSigningSecret] = useState("");
  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const [tunnelToken, setTunnelToken] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const reset = () => {
    setChannelType("telegram");
    setName("");
    setBotToken("");
    setAppId("");
    setAppSecret("");
    setSigningSecret("");
    setPublicBaseUrl("");
    setTunnelToken("");
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
        ? { channel_type: "telegram", name, bot_token: botToken }
        : {
            channel_type: "seatalk",
            name,
            app_id: appId,
            app_secret: appSecret,
            signing_secret: signingSecret,
            public_base_url: publicBaseUrl,
            tunnel_token: tunnelToken,
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
          {channelType === "telegram" ? (
            <div className="space-y-2">
              <Label htmlFor="channel-bot-token">{t("channels.dialog.botToken")}</Label>
              <PasswordInput
                id="channel-bot-token"
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">{t("channels.dialog.telegramHint")}</p>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="channel-app-id">{t("channels.dialog.appId")}</Label>
                <Input
                  id="channel-app-id"
                  value={appId}
                  onChange={(e) => setAppId(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="channel-app-secret">{t("channels.dialog.appSecret")}</Label>
                <PasswordInput
                  id="channel-app-secret"
                  value={appSecret}
                  onChange={(e) => setAppSecret(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="channel-signing-secret">{t("channels.dialog.signingSecret")}</Label>
                <PasswordInput
                  id="channel-signing-secret"
                  value={signingSecret}
                  onChange={(e) => setSigningSecret(e.target.value)}
                  autoComplete="off"
                />
                <p className="text-xs text-muted-foreground">{t("channels.dialog.seatalkHint")}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="channel-public-base-url">
                  {t("channels.dialog.publicBaseUrl")}
                </Label>
                <Input
                  id="channel-public-base-url"
                  value={publicBaseUrl}
                  onChange={(e) => setPublicBaseUrl(e.target.value)}
                  placeholder="https://xxx.trycloudflare.com"
                  autoComplete="off"
                />
                <p className="text-xs text-muted-foreground">
                  {t("channels.dialog.publicBaseUrlHint")}
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="channel-tunnel-token">{t("channels.dialog.tunnelToken")}</Label>
                <PasswordInput
                  id="channel-tunnel-token"
                  value={tunnelToken}
                  onChange={(e) => setTunnelToken(e.target.value)}
                  autoComplete="off"
                />
                <p className="text-xs text-muted-foreground">
                  {t("channels.dialog.tunnelTokenHint")}
                </p>
              </div>
            </>
          )}
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
