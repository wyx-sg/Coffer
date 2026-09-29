// frontend/src/components/channel/EditChannelDialog.tsx
// Modal "Edit channel" dialog. Updates a channel's mutable config: rotate the
// platform secret(s) — the new value is written to the SAME credential ref the
// channel already points at, so a rotation never re-pairs or re-registers —
// re-bind the default agent (SeaTalk also exposes its app id), and set when
// the bot answers in a group (EditChannelGroupFields), and how long a burst of
// messages is held before it runs as one turn (EditChannelBurstFields). The bound
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
import { displayName, titlePatchValue } from "@/lib/resourceTitle";
import { ResourceTitleField } from "@/components/resource/ResourceTitleField";
import type { ResourceOut } from "@/lib/api/resources";
import { EditChannelSecretFields, type ChannelEditDraft } from "./EditChannelSecretFields";
import { EditChannelGroupFields, type ChannelGroupDraft } from "./EditChannelGroupFields";
import { EditChannelBurstFields, type ChannelBurstDraft } from "./EditChannelBurstFields";
import {
  burstDraftValid,
  honoursRequireMention,
  parseBurstWait,
  planChannelEdit,
  storedBurstWait,
} from "./editChannel";

function strField(config: Record<string, unknown>, key: string): string {
  const v = config[key];
  return typeof v === "string" ? v : "";
}

/** A stored bool, or the backend's default when the key is absent. */
function boolField(config: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const v = config[key];
  return typeof v === "boolean" ? v : fallback;
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
  const [title, setTitle] = useState(resource.title ?? "");
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
  // Group gating; the fallbacks are the backend defaults (mention required,
  // other @mentions not ignored).
  const storedGroup = (): ChannelGroupDraft => ({
    requireMention: boolField(config, "require_mention", true),
    ignoreOtherMentions: boolField(config, "ignore_other_mentions", false),
  });
  const [group, setGroup] = useState<ChannelGroupDraft>(storedGroup);
  const patchGroup = (patch: Partial<ChannelGroupDraft>) => setGroup((g) => ({ ...g, ...patch }));
  // Message batching; an absent key shows the backend default (1.5s / 5s).
  const storedBurst = (): ChannelBurstDraft => ({
    waitAfterText: String(storedBurstWait(config, "wait_after_text_seconds")),
    waitAfterForward: String(storedBurstWait(config, "wait_after_forward_seconds")),
  });
  const [burst, setBurst] = useState<ChannelBurstDraft>(storedBurst);
  const patchBurst = (patch: Partial<ChannelBurstDraft>) => setBurst((b) => ({ ...b, ...patch }));
  const burstValid = burstDraftValid(burst);

  const reset = () => {
    setDefaultAgent(strField(config, "default_agent"));
    setTitle(resource.title ?? "");
    setSecrets(storedSecrets());
    setGroup(storedGroup());
    setBurst(storedBurst());
  };

  const seatalk = channelType === "seatalk";

  const submit = () => {
    if (!burstValid) return;
    const nextTitle = titlePatchValue(title);
    const plan = planChannelEdit({
      uid: resource.uid,
      name: displayName({ name: resource.name, title: nextTitle }),
      title: nextTitle !== (resource.title ?? null) ? nextTitle : undefined,
      config,
      values: {
        default_agent: defaultAgent,
        app_id: seatalk ? secrets.appId : undefined,
        bot_token: secrets.botToken,
        app_secret: secrets.appSecret,
        require_mention: honoursRequireMention(channelType) ? group.requireMention : undefined,
        ignore_other_mentions: group.ignoreOtherMentions,
        wait_after_text_seconds: parseBurstWait(burst.waitAfterText) ?? undefined,
        wait_after_forward_seconds: parseBurstWait(burst.waitAfterForward) ?? undefined,
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
      <DialogContent>
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
          <ResourceTitleField
            id="edit-channel-title"
            value={title}
            onChange={setTitle}
            name={resource.name}
          />

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

          <EditChannelGroupFields channelType={channelType} draft={group} onChange={patchGroup} />

          <EditChannelBurstFields draft={burst} onChange={patchBurst} />

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={update.isPending || !burstValid}>
              {update.isPending ? t("common.saving") : t("channels.edit.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
