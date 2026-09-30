// src/components/custom-tools/EditGroupDialog.tsx — change a group's description, base URL, auth header and
// secret (or none), and timeout. The name is fixed: it is the prefix agents see.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/lib/api/errors";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { authBody, authDraftOf, type AuthDraft } from "@/lib/customTools/drafts";
import { useUpdateCustomToolGroup } from "@/lib/hooks/useCustomTools";
import { AuthFields } from "./AuthFields";
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
  const [auth, setAuth] = useState<AuthDraft>(authDraftOf(group));
  const [timeout, setTimeoutSeconds] = useState("30");

  useEffect(() => {
    if (!open) return;
    setDescription(group.description ?? "");
    setBaseUrl(group.base_url);
    setAuth(authDraftOf(group));
    setTimeoutSeconds(String(group.timeout_seconds));
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on opening
  }, [open]);

  const seconds = Number(timeout);
  const timeoutOk = Number.isInteger(seconds) && seconds >= 1 && seconds <= 300;
  const ready = baseUrl.trim() !== "" && timeoutOk;
  const onSave = () =>
    update.mutate(
      {
        description: description.trim() || null,
        base_url: baseUrl.trim(),
        auth: authBody(auth),
        timeout_seconds: seconds,
      },
      { onSuccess: () => onOpenChange(false) },
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[520px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("customTools.editGroup.title", { name: group.name })}</DialogTitle>
          <DialogDescription>{t("customTools.editGroup.subtitle")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField label={t("customTools.editGroup.description")} htmlFor={`${id}-desc`}>
            <Textarea
              id={`${id}-desc`}
              rows={2}
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
            label={t("customTools.editGroup.timeout")}
            htmlFor={`${id}-timeout`}
            help={t("customTools.editGroup.timeoutHelp")}
            error={timeoutOk ? undefined : t("customTools.editGroup.timeoutInvalid")}
          >
            <Input
              id={`${id}-timeout`}
              type="number"
              min={1}
              max={300}
              className="w-28"
              value={timeout}
              onChange={(e) => setTimeoutSeconds(e.target.value)}
            />
          </FormField>
          {update.error ? (
            <div role="alert" className="flex items-start gap-2 text-sm text-danger">
              <AlertCircle className="mt-0.5 size-[15px] shrink-0" aria-hidden />
              <span>{translateApiError(t, update.error)}</span>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
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
