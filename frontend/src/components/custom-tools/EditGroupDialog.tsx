// src/components/custom-tools/EditGroupDialog.tsx — Edit group (4.2.35, 640): its description and timeout. Base URLs,
// headers, secrets and variables belong to the environments and are edited from their rows, however many there are.
// The name is fixed: it is the prefix agents see. Reach is the header's Reach control, not a field here.
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
import type { CustomToolGroup, ResponseRule } from "@/lib/api/customTools";
import { diagnosticHeadersProblem, rulesValid, splitList } from "@/lib/customTools/responseRules";
import { agentPrefix } from "@/lib/customTools/groups";
import { useUpdateCustomToolGroup } from "@/lib/hooks/useCustomTools";
import { FormField } from "./FormField";
import { GroupDescriptionField } from "./GroupDescriptionField";
import { GroupResponseFields } from "./GroupResponseFields";

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
  const [timeout, setTimeoutSeconds] = useState("30");
  const [diagnostic, setDiagnostic] = useState("");
  const [rules, setRules] = useState<ResponseRule[]>([]);
  // The rule editor reads its rules once, so it starts over each time the dialog opens.
  const [opened, setOpened] = useState(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDescription(group.description ?? "");
    setTimeoutSeconds(String(group.timeout_seconds));
    setDiagnostic((group.response?.diagnostic_headers ?? []).join(", "));
    setRules(group.response?.rules ?? []);
    setOpened((n) => n + 1);
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const seconds = Number(timeout.replace(/\s*s$/, ""));
  const timeoutOk = Number.isInteger(seconds) && seconds >= 1 && seconds <= 300;
  const ready =
    timeoutOk && rulesValid(rules) && diagnosticHeadersProblem(splitList(diagnostic)) === null;
  const error = update.error;
  const onSave = () => {
    setSaving(true);
    update.mutate(
      {
        description: description.trim() || null,
        timeout_seconds: seconds,
        response: { diagnostic_headers: splitList(diagnostic), rules },
      },
      {
        onSuccess: () => onOpenChange(false),
        onSettled: () => setSaving(false),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] max-w-[640px] overflow-y-auto"
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
          <GroupDescriptionField value={description} onChange={setDescription} />
          <p className="text-xs text-text-muted">{t("customTools.editGroup.environmentsNote")}</p>
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
          <GroupResponseFields
            key={opened}
            headers={diagnostic}
            onHeaders={setDiagnostic}
            rules={rules}
            onRules={setRules}
          />
          {error ? (
            <div role="alert" className="flex items-start gap-2 text-sm text-danger">
              <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
              <span>{translateApiError(t, error)}</span>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!ready || saving} onClick={onSave}>
            {saving ? t("common.saving") : error ? t("common.retry") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
