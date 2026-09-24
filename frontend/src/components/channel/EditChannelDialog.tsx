// frontend/src/components/channel/EditChannelDialog.tsx
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
import { AgentSelect } from "@/components/agents/AgentSelect";
import { useUpdateChannel } from "@/lib/hooks/useChannels";
import type { ResourceOut } from "@/lib/api/resources";
import { EditChannelSecretFields, type ChannelEditDraft } from "./EditChannelSecretFields";
import { planChannelEdit } from "./editChannel";

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
  // The picker is AgentSelect: `default_agent` holds an agent RESOURCE UID, and
  // so does every other reference to an agent, so there is one list to read and
  // nothing to translate. (It used to read the chat provider registry, because
  // the binding was a provider KEY while the scope beside it held resource
  // names — two vocabularies for one thing, which is what this change removes.)
  const [defaultAgent, setDefaultAgent] = useState(strField(config, "default_agent"));
  // The credential inputs. The rotation fields start blank on purpose: blank
  // means "leave the stored secret alone".
  const storedSecrets = (): ChannelEditDraft => ({
    appId: strField(config, "app_id"),
    botToken: "",
    appSecret: "",
  });
  const [secrets, setSecrets] = useState<ChannelEditDraft>(storedSecrets);
  const patchSecrets = (patch: Partial<ChannelEditDraft>) =>
    setSecrets((s) => ({ ...s, ...patch }));

  const reset = () => {
    setDefaultAgent(strField(config, "default_agent"));
    setSecrets(storedSecrets());
  };

  const seatalk = channelType === "seatalk";

  const submit = () => {
    const plan = planChannelEdit({
      uid: resource.uid,
      name: resource.name,
      config,
      values: {
        default_agent: defaultAgent,
        app_id: seatalk ? secrets.appId : undefined,
        bot_token: secrets.botToken,
        app_secret: secrets.appSecret,
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
            {/* A binding this vault has no agent for is kept and shown as the
                uid it is, rather than dropped — see AgentSelect. */}
            <AgentSelect
              id="edit-channel-agent"
              label={t("channels.edit.agent")}
              value={defaultAgent}
              onChange={setDefaultAgent}
            />
            <p className="text-xs text-muted-foreground">{t("channels.edit.agentHint")}</p>
          </div>

          <EditChannelSecretFields
            channelType={channelType}
            draft={secrets}
            onChange={patchSecrets}
          />

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
