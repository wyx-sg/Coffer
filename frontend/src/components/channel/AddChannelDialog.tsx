// frontend/src/components/channel/AddChannelDialog.tsx
// Modal "Add channel" dialog. The user picks a type (Telegram / SeaTalk),
// names the channel, and pastes the platform secrets; registration plumbing
// (secrets-first write + rollback) lives in registerChannel.ts.
//
// Validation issues land under the field they name, translated (the schema's
// messages are i18n keys) — never zod's own text, never a toast. Only a server
// failure is toasted, and it is also stated inline so the dialog explains
// itself once the toast is gone.
//
// The channel is bound to THIS machine at creation (spec channels, "Where a
// channel runs"): a channel that names no machine is one no daemon will start,
// and "I filled in the form and the bot never answered" is the worst possible
// first experience of the feature. The binding is movable afterwards from the
// list row or the detail page.
//
// The form ASKS which agent the channel drives (AgentSelect). It used to send
// a constant — the `claude_code` provider key — because the binding was
// expressed in a vocabulary every install shared. It is an agent resource's uid
// now, minted per vault, so there is no constant to send and the only honest
// thing a create form can do is offer the agents this vault actually has.
//
// Validation lives in `addChannel.ts`, beside `editChannel.ts`, so this file is
// the markup and the sequencing and neither file is both.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AgentSelect } from "@/components/agents/AgentSelect";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { useAgents } from "@/lib/hooks/useAgents";
import { translateApiError } from "@/lib/api/errors";
import { useSyncStatus } from "@/lib/hooks/useSync";
import type { ChannelDelivery, ChannelType } from "@/lib/api/channels";
import { useCreateChannel } from "@/lib/hooks/useChannels";
import { EMPTY_SECRET_DRAFT, validateAddChannel } from "./addChannel";
import {
  AddChannelSecretFields,
  type ChannelFieldErrors,
  type ChannelSecretDraft,
} from "./AddChannelSecretFields";
import { FieldError, RequiredLabel } from "./RequiredLabel";
import { DEFAULT_DELIVERY, planChannel, type ChannelPlan } from "./schema";

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
  // This machine's id, which the new channel is bound to. It is read here and
  // passed into the planner rather than fetched there, so planning stays pure.
  const { data: syncStatus } = useSyncStatus();
  const machineId = syncStatus?.machine_id ?? null;
  // The agents this vault has, and the one the new channel will drive. The
  // form opens on the first of them rather than on nothing: a channel bound to
  // nobody never answers, so "none" is not a state the form may produce.
  const { data: agents } = useAgents();
  const [agentUid, setAgentUid] = useState("");
  const defaultAgentUid = agentUid || (agents?.[0]?.uid ?? "");
  const [channelType, setChannelType] = useState<ChannelType>("telegram");
  const [delivery, setDelivery] = useState<ChannelDelivery>(DEFAULT_DELIVERY);
  const [name, setName] = useState("");
  const [secrets, setSecrets] = useState<ChannelSecretDraft>(EMPTY_SECRET_DRAFT);
  const patchSecrets = (patch: Partial<ChannelSecretDraft>) =>
    setSecrets((s) => ({ ...s, ...patch }));
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<ChannelFieldErrors>({});

  /**
   * Switching transport drops what the other method owns — the config may not
   * carry both, and a value the form no longer shows must not be submitted.
   */
  const changeDelivery = (next: ChannelDelivery) => {
    setDelivery(next);
    setFormError(null);
    setFieldErrors({});
    if (next === "websocket") {
      patchSecrets({ signingSecret: "", publicBaseUrl: "", tunnelToken: "" });
    }
  };

  const reset = () => {
    setAgentUid("");
    setChannelType("telegram");
    setDelivery(DEFAULT_DELIVERY);
    setName("");
    setSecrets(EMPTY_SECRET_DRAFT);
    setFormError(null);
    setFieldErrors({});
  };

  // The hook invalidates the resources cache and toasts on error; what the
  // dialog itself does with the outcome stays here.
  const create = useCreateChannel();
  const runCreate = (plan: ChannelPlan) =>
    create.mutate(plan, {
      // The registration hands back the whole resource: the name for the
      // toast, the uid for the link. Two answers, and no longer one string.
      onSuccess: (created) => {
        toast.success(t("channels.dialog.created", { name: created.name }));
        reset();
        onOpenChange(false);
        navigate(`/channels/${encodeURIComponent(created.uid)}`);
      },
      onError: (e) => setFormError(translateApiError(t, e)),
    });

  const submit = () => {
    setFormError(null);
    setFieldErrors({});
    const parsed = validateAddChannel({ channelType, delivery, name, secrets }, t);
    if (!parsed.ok) {
      setFieldErrors(parsed.fieldErrors);
      return;
    }
    // A channel is bound to the machine it is created from. Without this
    // machine's id there is nothing to bind it to, and registering anyway
    // would produce a channel that runs nowhere — so the form says why and
    // stays open rather than creating a bot that will never answer.
    if (machineId === null) {
      setFormError(t("channels.dialog.machineUnknown"));
      return;
    }
    // Same rule for the agent: a channel bound to nobody is a bot that never
    // answers, and the form says so rather than registering one.
    if (defaultAgentUid === "") {
      setFormError(t("channels.dialog.errors.agent"));
      return;
    }
    runCreate(planChannel(parsed.values, machineId, defaultAgentUid));
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
            <Label htmlFor="channel-agent">{t("channels.dialog.agent")}</Label>
            <AgentSelect
              id="channel-agent"
              label={t("channels.dialog.agent")}
              value={defaultAgentUid}
              onChange={setAgentUid}
            />
            <p className="text-xs text-muted-foreground">{t("channels.dialog.agentHint")}</p>
          </div>
          <div className="space-y-2">
            <RequiredLabel htmlFor="channel-name">{t("channels.dialog.name")}</RequiredLabel>
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
          </div>
          <AddChannelSecretFields
            channelType={channelType}
            delivery={delivery}
            onDeliveryChange={changeDelivery}
            draft={secrets}
            errors={fieldErrors}
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
