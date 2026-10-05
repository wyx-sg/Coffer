// src/components/custom-tools/EnvironmentDialog.tsx — Add environment / Edit environment (4.2.28): its name, base URL,
// headers (a plain value, or a secret from Coffer behind an optional scheme), variables and timeout. The group's
// tools are not copied: an environment is only where the same tools are sent (spec mcp-gateway "Keep a custom-tool
// group's environments in the group"). A new base URL, or a secret bound to a header, waits for approval before any
// request carries the secret, and only for this environment.
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
import type { CustomToolEnvironment, CustomToolGroup } from "@/lib/api/customTools";
import { useSaveCustomToolEnvironment } from "@/lib/hooks/useCustomToolEnvironments";
import { FormField } from "./FormField";
import { headerRowsOf, headersIn } from "./headerRows";
import { VariableRows } from "./VariableRows";
import { variablesIn, type VariableRow } from "./environmentVariables";

interface Props {
  group: CustomToolGroup;
  /** The environment to edit; `null` adds one. */
  environment: CustomToolEnvironment | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EnvironmentDialog({ group, environment, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const save = useSaveCustomToolEnvironment(group.name);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [rows, setRows] = useState<KeyValueSecretRow[]>([]);
  const [variables, setVariables] = useState<VariableRow[]>([]);
  const [timeout, setTimeoutSeconds] = useState("");
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  useEffect(() => {
    if (!open) return;
    setName(environment?.name ?? "");
    setBaseUrl(environment?.base_url ?? "");
    setRows(environment ? headerRowsOf(environment) : []);
    setVariables(
      Object.entries(environment?.variables ?? {}).map(([key, value]) => ({ key, value })),
    );
    setTimeoutSeconds(environment?.timeout_seconds ? String(environment.timeout_seconds) : "");
    setFailure(null);
    save.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const seconds = timeout.trim() === "" ? null : Number(timeout.replace(/\s*s$/, ""));
  const timeoutOk =
    seconds === null || (Number.isInteger(seconds) && seconds >= 1 && seconds <= 300);
  const ready = name.trim() !== "" && baseUrl.trim() !== "" && timeoutOk;
  const error = failure ?? save.error;

  const onSave = async () => {
    setFailure(null);
    setSaving(true);
    try {
      // A secret typed into a row is written to Secrets before the environment names it.
      await persistNewSecrets(rows.map((r) => r.value));
    } catch (e) {
      setSaving(false);
      setFailure(e);
      return;
    }
    save.mutate(
      {
        name: environment?.name ?? null,
        body: {
          name: name.trim(),
          base_url: baseUrl.trim(),
          headers: headersIn(rows),
          variables: variablesIn(variables),
          timeout_seconds: seconds,
        },
      },
      { onSuccess: () => onOpenChange(false), onSettled: () => setSaving(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] max-w-[640px] overflow-y-auto"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle>
            {environment
              ? t("customTools.environments.editTitle", { name: environment.name })
              : t("customTools.environments.addTitle", { group: group.name })}
          </DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField
            label={t("customTools.environments.name")}
            htmlFor={`${id}-name`}
            required
            help={t("customTools.environments.nameHelp")}
          >
            <Input
              id={`${id}-name`}
              className="font-mono"
              placeholder="staging"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </FormField>
          <FormField
            label={t("customTools.fields.baseUrl")}
            htmlFor={`${id}-base`}
            required
            help={t("customTools.environments.baseUrlHelp")}
          >
            <Input
              id={`${id}-base`}
              className="font-mono"
              placeholder="https://api.example.com/v1"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </FormField>
          <FormField
            label={t("customTools.fields.headers")}
            help={t("customTools.environments.headersHelp")}
          >
            <KeyValueSecretRows
              rows={rows}
              onChange={setRows}
              label={t("customTools.fields.headers")}
              keyPlaceholder={t("customTools.editor.headerKey")}
              addLabel={t("customTools.editor.addHeader")}
              schemes
              secretLabelFor={(key) => `${group.name}-${name.trim() || "env"}-${key}`}
            />
          </FormField>
          <FormField
            label={t("customTools.environments.variables")}
            help={t("customTools.environments.variablesHelp")}
          >
            <VariableRows rows={variables} onChange={setVariables} />
          </FormField>
          <FormField
            label={t("customTools.editGroup.timeout")}
            htmlFor={`${id}-timeout`}
            help={t("customTools.environments.timeoutHelp", { seconds: group.timeout_seconds })}
            error={timeoutOk ? undefined : t("customTools.editGroup.timeoutInvalid")}
          >
            <div className="relative w-32">
              <Input
                id={`${id}-timeout`}
                inputMode="numeric"
                className="pr-7 font-mono"
                placeholder={String(group.timeout_seconds)}
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
