// frontend/src/kinds/channel/EditChannelDialog.tsx
// Modal "Edit channel" dialog. Updates a channel's mutable config: rotate the
// platform secret(s) — the new value is written to the SAME credential ref the
// channel already points at, so a rotation never re-pairs or re-registers —
// and re-bind the default agent (SeaTalk also exposes its app id). The bound
// agent's models all stay available; the model is switched in chat with
// /model. Apply plumbing (secrets-first write, then config PATCH) lives in
// editChannel.ts.
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useUpdateChannel } from "@/lib/hooks/useChannels";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import type { ChannelDelivery } from "@/lib/api/channels";
import { EditChannelSecretFields, type ChannelEditDraft } from "./EditChannelSecretFields";
import { DEFAULT_AGENT, DEFAULT_DELIVERY, planChannelEdit } from "./schema";

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
  const { data: agents } = useAgentProviders();

  const [defaultAgent, setDefaultAgent] = useState(
    strField(config, "default_agent") || DEFAULT_AGENT,
  );
  // The credential inputs. The rotation fields start blank on purpose: blank
  // means "leave the stored secret alone".
  const storedSecrets = (): ChannelEditDraft => ({
    appId: strField(config, "app_id"),
    publicBaseUrl: strField(config, "public_base_url"),
    tunnelToken: "",
    botToken: "",
    appSecret: "",
    signingSecret: "",
  });
  const [secrets, setSecrets] = useState<ChannelEditDraft>(storedSecrets);
  const patchSecrets = (patch: Partial<ChannelEditDraft>) =>
    setSecrets((s) => ({ ...s, ...patch }));
  const [formError, setFormError] = useState<string | null>(null);
  // Absent means webhook — every channel configured before websocket existed
  // is one, so the stored reality and this default agree.
  const storedDelivery = (): ChannelDelivery =>
    strField(config, "delivery") === "websocket" ? "websocket" : DEFAULT_DELIVERY;
  const [delivery, setDelivery] = useState<ChannelDelivery>(storedDelivery);

  /**
   * Switching transport clears what the other method owns: the backend rejects
   * a config carrying both, and the platform's own delivery setting must be
   * switched in step on SeaTalk's Developer Portal.
   */
  const changeDelivery = (next: ChannelDelivery) => {
    setDelivery(next);
    setFormError(null);
    if (next === "websocket") {
      patchSecrets({ signingSecret: "", publicBaseUrl: "", tunnelToken: "" });
    }
  };

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
    setSecrets(storedSecrets());
    setDelivery(storedDelivery());
    setFormError(null);
  };

  const seatalk = channelType === "seatalk";

  const submit = () => {
    setFormError(null);
    // Webhook delivery cannot exist without a signing secret, so a switch back
    // to it asks for one here rather than failing on the backend's validator.
    if (seatalk && delivery === "webhook" && !config.signing_secret_ref && !secrets.signingSecret) {
      setFormError(t("channels.edit.signingSecretRequired"));
      return;
    }
    const plan = planChannelEdit({
      name: resource.name,
      config,
      values: {
        default_agent: defaultAgent,
        app_id: seatalk ? secrets.appId : undefined,
        delivery: seatalk ? delivery : undefined,
        bot_token: secrets.botToken,
        app_secret: secrets.appSecret,
        signing_secret: secrets.signingSecret,
        public_base_url: seatalk ? secrets.publicBaseUrl : undefined,
        tunnel_token: seatalk ? secrets.tunnelToken : undefined,
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

          <EditChannelSecretFields
            channelType={channelType}
            delivery={delivery}
            onDeliveryChange={changeDelivery}
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
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? t("common.saving") : t("channels.edit.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
