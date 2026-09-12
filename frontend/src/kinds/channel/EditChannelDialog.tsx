// frontend/src/kinds/channel/EditChannelDialog.tsx
// Modal "Edit channel" dialog. Updates a channel's mutable config: rotate the
// platform secret(s) — the new value is written to the SAME credential ref the
// channel already points at, so a rotation never re-pairs or re-registers —
// and re-bind the default agent (SeaTalk also exposes its app id), plus the
// channel's own model curation — its default model and allowed range (FR-071),
// which live in ChannelModelFields. Apply plumbing (secrets-first write, then
// config PATCH) lives in editChannel.ts.
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
import { ChannelModelFields } from "./ChannelModelFields";
import { EditChannelSecretFields, type ChannelEditDraft } from "./EditChannelSecretFields";
import { defaultModelOutOfRange } from "./modelCuration";
import { DEFAULT_AGENT, planChannelEdit } from "./schema";

function strField(config: Record<string, unknown>, key: string): string {
  const v = config[key];
  return typeof v === "string" ? v : "";
}

/** The stored allowed range, or `[]` when the channel curates none. */
function modelsField(config: Record<string, unknown>): string[] {
  const v = config.models;
  return Array.isArray(v) ? v.filter((m): m is string => typeof m === "string") : [];
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
  const [defaultModel, setDefaultModel] = useState(strField(config, "default_model"));
  const [models, setModels] = useState<string[]>(modelsField(config));
  const [formError, setFormError] = useState<string | null>(null);

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
    setDefaultModel(strField(config, "default_model"));
    setModels(modelsField(config));
    setFormError(null);
  };

  const submit = () => {
    setFormError(null);
    // Mirrors the backend's own rule (FR-071) so a save cannot fail on
    // something the form is already showing.
    if (defaultModelOutOfRange(defaultModel, models)) {
      setFormError(t("channels.models.outOfRange"));
      return;
    }
    const plan = planChannelEdit({
      name: resource.name,
      config,
      values: {
        default_agent: defaultAgent,
        app_id: channelType === "seatalk" ? secrets.appId : undefined,
        bot_token: secrets.botToken,
        app_secret: secrets.appSecret,
        signing_secret: secrets.signingSecret,
        public_base_url: channelType === "seatalk" ? secrets.publicBaseUrl : undefined,
        tunnel_token: channelType === "seatalk" ? secrets.tunnelToken : undefined,
        default_model: defaultModel,
        models,
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

          {/* Keyed by the BOUND agent: the ids below are that agent's, and the
              fields clear themselves when the binding changes. */}
          <ChannelModelFields
            agentKey={defaultAgent}
            defaultModel={defaultModel}
            models={models}
            onDefaultModelChange={setDefaultModel}
            onModelsChange={setModels}
            idPrefix="edit-channel"
          />

          <EditChannelSecretFields
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
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? t("common.saving") : t("channels.edit.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
