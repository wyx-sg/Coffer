// src/components/credentials/AddSecretDialog.tsx — Add secret: a standalone secret under `secret/<name>`.
//
// The name is fixed once added, because files cite it (spec secret
// "Resolve standalone secrets into one child with coffer run"). A name that
// already exists is caught before sending, with a way to replace that
// secret's value instead. The value is never shown back. A new secret waits,
// sealed, for approval in the Coffer app (202, spec secret "Hold a new
// standalone secret until a person approves it"): the dialog closes on a toast
// that says so, and the approvals banner offers Review.
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
import { PasswordInput } from "@/components/ui/password-input";
import { useToast } from "@/components/ui/toast";
import type { CredentialRef } from "@/lib/api/credentials";
import { translateApiError } from "@/lib/api/errors";
import { useSetSecret } from "@/lib/hooks/useSecrets";
import { SECRET_PREFIX, isValidSecretName } from "./secretRows";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existing: CredentialRef[];
  /** The name is taken: replace that secret's value instead. */
  onReplaceInstead: (row: CredentialRef) => void;
}

const LABEL = "text-xs font-label text-text";

export function AddSecretDialog({ open, onOpenChange, existing, onReplaceInstead }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const set = useSetSecret();
  const nameId = useId();
  const valueId = useId();
  const [name, setName] = useState("");
  const [value, setValue] = useState("");

  const { reset } = set;
  useEffect(() => {
    if (!open) return;
    setName("");
    setValue("");
    reset();
  }, [open, reset]);

  const trimmed = name.trim();
  const taken = existing.find((r) => r.present && r.ref === `${SECRET_PREFIX}${trimmed}`);
  const invalid = trimmed !== "" && !isValidSecretName(trimmed);
  const canSubmit = trimmed !== "" && !invalid && !taken && value !== "" && !set.isPending;

  const submit = async () => {
    if (!canSubmit) return;
    try {
      const out = await set.mutateAsync({ ref: `${SECRET_PREFIX}${trimmed}`, value });
      toast.success(
        out?.approval ? t("secrets.pending.toast") : t("secrets.add.added", { name: trimmed }),
      );
      onOpenChange(false);
    } catch {
      // Shown inline from the mutation's error.
    }
  };

  const nameError = taken ? (
    <p role="alert" className="flex flex-wrap items-center gap-x-2 text-xs text-danger">
      {t("secrets.add.nameTaken", { name: trimmed })}
      <Button
        type="button"
        variant="link"
        size="sm"
        className="h-auto p-0"
        onClick={() => onReplaceInstead(taken)}
      >
        {t("secrets.add.replaceInstead")}
      </Button>
    </p>
  ) : invalid ? (
    <p role="alert" className="text-xs text-danger">
      {t("secrets.add.nameInvalid")}
    </p>
  ) : (
    <p className="text-xs text-text-muted">{t("secrets.add.nameHint")}</p>
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !set.isPending && onOpenChange(next)}>
      <DialogContent className="max-w-[480px]">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("secrets.add.title")}</DialogTitle>
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
              aria-invalid={Boolean(taken || invalid)}
              onChange={(e) => setName(e.target.value)}
            />
            {nameError}
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={valueId} className={LABEL}>
              {t("secrets.add.value")}
            </label>
            <PasswordInput
              id={valueId}
              value={value}
              autoComplete="off"
              onChange={(e) => setValue(e.target.value)}
            />
            <p className="text-xs text-text-muted">{t("secrets.add.valueHint")}</p>
          </div>
          <p className="rounded-md bg-surface-sunken px-3 py-2 text-xs text-text-muted">
            {t("secrets.add.encrypted", {
              reference: `coffer://secret/${trimmed || t("secrets.add.namePlaceholder")}`,
            })}
          </p>
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
              {set.isPending ? t("secrets.add.submitting") : t("secrets.add.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
