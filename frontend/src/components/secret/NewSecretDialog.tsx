// src/components/secret/NewSecretDialog.tsx — New secret…: the small dialog a secret field's menu opens.
// Name + value → written to Secrets → the caller selects it. A write held for
// approval closes on the same toast the Add secret dialog gives.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

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
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useSecretChoices } from "./useSecretChoices";
import { useSetSecret } from "@/lib/hooks/useSecrets";
import { secretRef } from "./secretValue";
import { isValidSecretName } from "./secretRows";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The name the dialog opens with. */
  defaultName?: string;
  /** The secret now exists (or waits for approval): select it. */
  onCreated: (name: string) => void;
}

const LABEL = "text-xs font-label text-text";

export function NewSecretDialog({ open, onOpenChange, defaultName = "", onCreated }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const set = useSetSecret();
  const { names } = useSecretChoices();
  const nameId = useId();
  const valueId = useId();
  const [name, setName] = useState("");
  const [value, setValue] = useState("");

  const { reset } = set;
  useEffect(() => {
    if (!open) return;
    setName(defaultName);
    setValue("");
    reset();
  }, [open, defaultName, reset]);

  const trimmed = name.trim();
  const taken = names.has(trimmed);
  const invalid = trimmed !== "" && !isValidSecretName(trimmed);
  const canSubmit = trimmed !== "" && !invalid && !taken && value !== "" && !set.isPending;

  const submit = async () => {
    if (!canSubmit) return;
    try {
      await set.mutateAsync({ ref: secretRef(trimmed), value });
      toast.success(t("secrets.add.added", { name: trimmed }));
      onCreated(trimmed);
      onOpenChange(false);
    } catch {
      // Shown inline from the mutation's error.
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !set.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-[480px]">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            void submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("secretField.dialog.title")}</DialogTitle>
            <DialogDescription className="sr-only">{t("secrets.subtitle")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={nameId} className={LABEL}>
              {t("secrets.add.name")}
            </label>
            <Input
              id={nameId}
              value={name}
              autoComplete="off"
              spellCheck={false}
              className="font-mono"
              aria-invalid={taken || invalid}
              onChange={(e) => setName(e.target.value)}
            />
            {taken || invalid ? (
              <p role="alert" className="text-xs text-danger">
                {taken
                  ? t("secretField.dialog.taken", { name: trimmed })
                  : t("secrets.add.nameInvalid")}
              </p>
            ) : (
              <p className="text-xs text-text-muted">{t("secrets.add.nameHint")}</p>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={valueId} className={LABEL}>
              {t("secrets.add.value")}
            </label>
            <Input
              id={valueId}
              type="password"
              value={value}
              autoComplete="off"
              onChange={(e) => setValue(e.target.value)}
            />
            <p className="text-xs text-text-muted">{t("secrets.add.valueHint")}</p>
          </div>
          {set.error ? (
            <p role="alert" className="text-xs text-danger">
              {translateApiError(t, set.error)}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {set.isPending
                ? t("secrets.add.submitting")
                : set.error
                  ? t("common.retry")
                  : t("secrets.add.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
