// src/components/custom-tools/EditGroupDialog.tsx — Edit group: its description, base URL, auth header and
// secret (or none), default reach and timeout. The name is fixed: it is the prefix agents see.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { authBody, authDraftOf, type AuthDraft } from "@/lib/customTools/drafts";
import { agentPrefix } from "@/lib/customTools/groups";
import { useUpdateCustomToolGroup } from "@/lib/hooks/useCustomTools";
import { AuthFields } from "./AuthFields";
import { DraftReachField } from "./DraftReachField";
import { FormField } from "./FormField";
import { sameReach } from "./toolForm";

interface Props {
  group: CustomToolGroup;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditGroupDialog({ group, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const update = useUpdateCustomToolGroup(group.name);
  const [description, setDescription] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [auth, setAuth] = useState<AuthDraft>(authDraftOf(group));
  const [agents, setAgents] = useState<string[] | null>(group.scope);
  const [timeout, setTimeoutSeconds] = useState("30");

  useEffect(() => {
    if (!open) return;
    setDescription(group.description ?? "");
    setBaseUrl(group.base_url);
    setAuth(authDraftOf(group));
    setAgents(group.scope);
    setTimeoutSeconds(String(group.timeout_seconds));
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const seconds = Number(timeout.replace(/\s*s$/, ""));
  const timeoutOk = Number.isInteger(seconds) && seconds >= 1 && seconds <= 300;
  const ready = baseUrl.trim() !== "" && timeoutOk;
  const onSave = () =>
    update.mutate(
      {
        body: {
          description: description.trim() || null,
          base_url: baseUrl.trim(),
          auth: authBody(auth),
          timeout_seconds: seconds,
        },
        agents: sameReach(agents, group.scope) ? undefined : agents,
      },
      { onSuccess: () => onOpenChange(false) },
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] max-w-[560px] overflow-y-auto"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle>{t("customTools.editGroup.title", { name: group.name })}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField
            label={t("customTools.editGroup.name")}
            htmlFor={`${id}-name`}
            help={t("customTools.editGroup.nameHelp", { prefix: agentPrefix(group.name) })}
          >
            <Input id={`${id}-name`} className="font-mono" value={group.name} disabled readOnly />
          </FormField>
          <FormField
            label={t("customTools.editGroup.description")}
            htmlFor={`${id}-desc`}
            help={t("customTools.editGroup.descriptionHelp")}
          >
            <Input
              id={`${id}-desc`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </FormField>
          <FormField
            label={t("customTools.fields.baseUrl")}
            htmlFor={`${id}-base`}
            required
            help={t("customTools.fields.baseUrlHelp")}
          >
            <Input
              id={`${id}-base`}
              className="font-mono"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </FormField>
          <AuthFields value={auth} onChange={setAuth} />
          <FormField
            label={t("customTools.fields.availableTo")}
            help={t("customTools.fields.availableToHelp")}
          >
            <DraftReachField value={agents} onChange={setAgents} />
          </FormField>
          <FormField
            label={t("customTools.editGroup.timeout")}
            htmlFor={`${id}-timeout`}
            help={t("customTools.editGroup.timeoutHelp")}
            error={timeoutOk ? undefined : t("customTools.editGroup.timeoutInvalid")}
          >
            <div className="relative w-32">
              <Input
                id={`${id}-timeout`}
                inputMode="numeric"
                className="pr-7 font-mono"
                value={timeout}
                onChange={(e) => setTimeoutSeconds(e.target.value)}
              />
              <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 font-mono text-xs text-text-muted">
                s
              </span>
            </div>
          </FormField>
          {update.error ? (
            <div role="alert" className="flex items-start gap-2 text-sm text-danger">
              <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
              <span>{translateApiError(t, update.error)}</span>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!ready || update.isPending} onClick={onSave}>
            {update.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
