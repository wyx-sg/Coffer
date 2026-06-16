// frontend/src/kinds/channel/EditChannelDialog.tsx
// Modal "Edit channel" dialog. Updates a channel's mutable config: rotate the
// platform secret(s) — the new value is written to the SAME credential ref the
// channel already points at, so a rotation never re-pairs or re-registers —
// and re-bind the default agent (SeaTalk also exposes its app id). Apply
// plumbing (secrets-first write, then config PATCH) lives in editChannel.ts.
import { useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useChatAgents } from "@/lib/hooks/useChatAgents";
import { useUpdateChannel } from "@/lib/hooks/useChannels";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import { DEFAULT_AGENT, planChannelEdit } from "./schema";

function strField(config: Record<string, unknown>, key: string): string {
  const v = config[key];
  return typeof v === "string" ? v : "";
}

export function EditChannelDialog({
  open,
  onOpenChange,
  resource,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  resource: ResourceOut;
}) {
  const { t } = useTranslation();
  const config = resource.config as Record<string, unknown>;
  const channelType = strField(config, "channel_type") || "telegram";
  const update = useUpdateChannel();
  // Source the picker from the chat provider registry (provider keys like
  // claude_code) — the same registry the turn resolves by — not the resource
  // list (names like claude-code), which would re-bind to an agent that fails
  // at turn time with UNKNOWN_AGENT.
  const { data: agents } = useChatAgents();

  const [defaultAgent, setDefaultAgent] = useState(
    strField(config, "default_agent") || DEFAULT_AGENT,
  );
  const [appId, setAppId] = useState(strField(config, "app_id"));
  const [botToken, setBotToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [signingSecret, setSigningSecret] = useState("");
  const [publicBaseUrl, setPublicBaseUrl] = useState(strField(config, "public_base_url"));
  const [tunnelToken, setTunnelToken] = useState("");

  // Offer the registered provider keys, plus the channel's current binding so a
  // value that is still loading or since-removed (e.g. a legacy "builtin")
  // stays shown until the owner picks a valid one. De-duped, keyed by provider
  // key; the human-readable display name is looked up per key.
  const agentLabels = new Map((agents ?? []).map((a) => [a.agent_key, a.display_name]));
  const agentOptions = Array.from(
    new Set([defaultAgent, ...(agents ?? []).map((a) => a.agent_key)]),
  );

  const reset = () => {
    setDefaultAgent(strField(config, "default_agent") || DEFAULT_AGENT);
    setAppId(strField(config, "app_id"));
    setBotToken("");
    setAppSecret("");
    setSigningSecret("");
    setPublicBaseUrl(strField(config, "public_base_url"));
    setTunnelToken("");
  };

  const submit = () => {
    const plan = planChannelEdit({
      name: resource.name,
      config,
      values: {
        default_agent: defaultAgent,
        app_id: channelType === "seatalk" ? appId : undefined,
        bot_token: botToken,
        app_secret: appSecret,
        signing_secret: signingSecret,
        public_base_url: channelType === "seatalk" ? publicBaseUrl : undefined,
        tunnel_token: channelType === "seatalk" ? tunnelToken : undefined,
      },
    });
    update.mutate(plan, {
      onSuccess: () => {
        reset();
        onOpenChange(false);
      },
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          update.reset();
          reset();
        }
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("channels.edit.title")}</DialogTitle>
          <DialogDescription>{t("channels.edit.subtitle")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="edit-channel-agent">{t("channels.edit.agent")}</Label>
            <Select value={defaultAgent} onValueChange={setDefaultAgent}>
              <SelectTrigger id="edit-channel-agent" aria-label={t("channels.edit.agent")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {agentOptions.map((a) => (
                  <SelectItem key={a} value={a}>
                    {agentLabels.get(a) ?? a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{t("channels.edit.agentHint")}</p>
          </div>

          {channelType === "seatalk" ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="edit-channel-app-id">{t("channels.dialog.appId")}</Label>
                <Input
                  id="edit-channel-app-id"
                  value={appId}
                  onChange={(e) => setAppId(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-channel-public-base-url">
                  {t("channels.dialog.publicBaseUrl")}
                </Label>
                <Input
                  id="edit-channel-public-base-url"
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
                <Label htmlFor="edit-channel-tunnel-token">
                  {t("channels.dialog.tunnelToken")}
                </Label>
                <PasswordInput
                  id="edit-channel-tunnel-token"
                  value={tunnelToken}
                  onChange={(e) => setTunnelToken(e.target.value)}
                  autoComplete="off"
                  placeholder={t("channels.edit.rotatePlaceholder")}
                />
                <p className="text-xs text-muted-foreground">
                  {t("channels.dialog.tunnelTokenHint")}
                </p>
              </div>
            </>
          ) : null}

          {channelType === "telegram" ? (
            <div className="space-y-2">
              <Label htmlFor="edit-channel-bot-token">{t("channels.edit.newBotToken")}</Label>
              <PasswordInput
                id="edit-channel-bot-token"
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
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
                  value={appSecret}
                  onChange={(e) => setAppSecret(e.target.value)}
                  autoComplete="off"
                  placeholder={t("channels.edit.rotatePlaceholder")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-channel-signing-secret">
                  {t("channels.edit.newSigningSecret")}
                </Label>
                <PasswordInput
                  id="edit-channel-signing-secret"
                  value={signingSecret}
                  onChange={(e) => setSigningSecret(e.target.value)}
                  autoComplete="off"
                  placeholder={t("channels.edit.rotatePlaceholder")}
                />
                <p className="text-xs text-muted-foreground">{t("channels.edit.rotateHint")}</p>
              </div>
            </>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? t("common.saving") : t("channels.edit.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
