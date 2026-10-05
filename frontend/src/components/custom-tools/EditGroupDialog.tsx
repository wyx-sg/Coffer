// src/components/custom-tools/EditGroupDialog.tsx — Edit group (4.2.05, 640): its description, base URL, headers (the
// shared header rows: a plain value or a secret from Coffer, the secret being the whole header value) and timeout.
// The name is fixed: it is the prefix agents see. Reach is the header's Reach control, not a field here.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { KeyValueSecretRows } from "@/components/secret/KeyValueSecretRows";
import { persistNewSecrets, type KeyValueSecretRow } from "@/components/secret/secretValue";
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
import { agentPrefix } from "@/lib/customTools/groups";
import { headerRowsOf, headersIn } from "./headerRows";
import { useUpdateCustomToolGroup } from "@/lib/hooks/useCustomTools";
import { FormField } from "./FormField";

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
  const [rows, setRows] = useState<KeyValueSecretRow[]>([]);
  const [timeout, setTimeoutSeconds] = useState("30");
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  useEffect(() => {
    if (!open) return;
    setDescription(group.description ?? "");
    setBaseUrl(group.base_url);
    setRows(headerRowsOf(group));
    setTimeoutSeconds(String(group.timeout_seconds));
    setFailure(null);
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const seconds = Number(timeout.replace(/\s*s$/, ""));
  const timeoutOk = Number.isInteger(seconds) && seconds >= 1 && seconds <= 300;
  const ready = baseUrl.trim() !== "" && timeoutOk;
  const error = failure ?? update.error;
  const onSave = async () => {
    setFailure(null);
    setSaving(true);
    try {
      // A secret typed into a row is written to Secrets before the group names it.
      await persistNewSecrets(rows.map((r) => r.value));
    } catch (e) {
      setSaving(false);
      setFailure(e);
      return;
    }
    update.mutate(
      {
        description: description.trim() || null,
        base_url: baseUrl.trim(),
        headers: headersIn(rows),
        timeout_seconds: seconds,
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
          <FormField
            label={t("customTools.fields.headers")}
            help={t("customTools.fields.headersHelp")}
          >
            <KeyValueSecretRows
              rows={rows}
              onChange={setRows}
              label={t("customTools.fields.headers")}
              keyPlaceholder={t("customTools.editor.headerKey")}
              addLabel={t("customTools.editor.addHeader")}
              secretLabelFor={(key) => `${group.name}-${key}`}
            />
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
          <Button disabled={!ready || saving} onClick={() => void onSave()}>
            {saving ? t("common.saving") : error ? t("common.retry") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
