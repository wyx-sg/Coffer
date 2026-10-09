// frontend/src/components/channel/AddChannelConnectStep.tsx
// Step 2 of Add channel: name it, choose the agent new conversations start
// on, and pick or paste the platform's credentials (the one secret field). Validation lands under the field
// it names (addChannel.ts; the schema's messages are i18n keys); a server
// failure is toasted by the hook and also stated inline.
//
// The channel drives the agent chosen here: `default_agent` is an agent
// resource uid, so the form offers this vault's agents and refuses to
// register a channel that drives nobody.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import { AgentSelect } from "@/components/agents/AgentSelect";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import type { ChannelType } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { useAgents } from "@/lib/hooks/useAgents";
import { useCreateChannel } from "@/lib/hooks/useChannels";
import { useCredentialCheck } from "@/lib/hooks/useCredentialCheck";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { EMPTY_SECRET_DRAFT, validateAddChannel } from "./addChannel";
import {
  AddChannelSecretFields,
  type ChannelFieldErrors,
  type ChannelSecretDraft,
} from "./AddChannelSecretFields";
import { ChannelCredentialNote } from "./ChannelCredentialNote";
import { FieldError } from "./FieldError";
import { planChannel } from "@/lib/channels/schema";

interface Props {
  platform: ChannelType;
  onBack: () => void;
  onCancel: () => void;
  onCreated: (channel: ResourceOut) => void;
}

export function AddChannelConnectStep({ platform, onBack, onCancel, onCreated }: Props) {
  const { t } = useTranslation();
  const { data: agents } = useAgents();
  const [agentUid, setAgentUid] = useState("");
  const defaultAgentUid = agentUid || (agents?.[0]?.uid ?? "");
  const [name, setName] = useState("");
  const [secrets, setSecrets] = useState<ChannelSecretDraft>(EMPTY_SECRET_DRAFT);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<ChannelFieldErrors>({});
  const create = useCreateChannel();
  // Telegram's token is checked as it is pasted (spec channels "Check
  // credentials before they are saved"); SeaTalk's is checked by connecting.
  // A stored token is not re-checked here: it is already in use, or was checked when it was added.
  const token = secrets.botToken?.kind === "new" ? secrets.botToken.value.trim() : "";
  const tokenCheck = useCredentialCheck(
    platform === "telegram" && token.length >= 10 ? { platform, bot_token: token } : null,
  );
  const machineName = useDaemonStatus().data?.machine_name ?? "";

  const submit = () => {
    setFormError(null);
    setFieldErrors({});
    const parsed = validateAddChannel({ channelType: platform, name, secrets }, t);
    if (!parsed.ok) {
      setFieldErrors(parsed.fieldErrors);
      return;
    }
    if (defaultAgentUid === "") {
      setFormError(t("channels.dialog.errors.agent"));
      return;
    }
    create.mutate(planChannel(parsed.values, defaultAgentUid), {
      onSuccess: onCreated,
      onError: (e) => setFormError(translateApiError(t, e)),
    });
  };

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="space-y-1.5">
        <Label required htmlFor="channel-name">
          {t("channels.dialog.name")}
        </Label>
        <Input
          id="channel-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("channels.dialog.namePlaceholder")}
          aria-required
          aria-invalid={fieldErrors.name ? true : undefined}
          aria-describedby="channel-name-error"
        />
        <FieldError id="channel-name-error" message={fieldErrors.name} />
        <p className="text-xs text-text-muted">{t("resources.freeName.hint")}</p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="channel-agent">{t("channels.dialog.agent")}</Label>
        <AgentSelect
          id="channel-agent"
          label={t("channels.dialog.agent")}
          value={defaultAgentUid}
          onChange={setAgentUid}
        />
        <p className="text-xs text-text-muted">{t("channels.dialog.agentHint")}</p>
      </div>
      <AddChannelSecretFields
        channelType={platform}
        channelName={name.trim()}
        draft={secrets}
        errors={fieldErrors}
        onChange={(patch) => setSecrets((s) => ({ ...s, ...patch }))}
      />
      {platform === "telegram" ? (
        <ChannelCredentialNote
          id="channel-bot-token-check"
          check={tokenCheck}
          success={(r) => ({
            title: r.bot_handle
              ? t("channels.dialog.telegramFound", { handle: r.bot_handle })
              : t("channels.dialog.telegramFoundPlain"),
            body: t("channels.dialog.telegramFoundBody", { machine: machineName }),
          })}
        />
      ) : null}
      {platform === "seatalk" ? (
        // A note, not an alert: nothing is wrong yet, and the step it names
        // only works once this connection exists.
        <div className="flex gap-2 rounded-lg bg-accent-soft px-3 py-2.5">
          <Info className="mt-0.5 size-[15px] shrink-0 text-accent-text" aria-hidden />
          <div className="space-y-0.5 text-xs">
            <p className="font-label text-text">{t("channels.dialog.seatalkDelivery.title")}</p>
            <p className="text-text-muted">{t("channels.dialog.seatalkDelivery.body")}</p>
          </div>
        </div>
      ) : null}
      {formError ? (
        <p className="text-sm text-danger" role="alert">
          {formError}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="ghost" className="mr-auto" onClick={onBack}>
          {t("channels.add.back")}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? t("channels.add.connecting") : t("channels.add.connect")}
        </Button>
      </DialogFooter>
    </form>
  );
}
