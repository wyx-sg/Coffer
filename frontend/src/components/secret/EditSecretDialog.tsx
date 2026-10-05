// src/components/secret/EditSecretDialog.tsx — Edit: a secret's name, description and value, in one dialog.
//
// Opened by Edit in the secret's header. The name and description are notes: saving them moves
// nothing that cites the secret (spec secret "Label and describe a secret without changing its
// reference"). The value field starts empty and is never filled with the old value; left empty the
// value stays, and a new one replaces it at once — or, for a secret missing on this Mac, stores it
// (spec secret "Store a secret through the API"). Only what changed is sent.
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
import type { SecretRef } from "@/lib/api/secret";
import { translateApiError } from "@/lib/api/errors";
import { useSecretNotes, useSetSecret } from "@/lib/hooks/useSecrets";
import { citersOf, DESCRIPTION_MAX, displayName, isMissingHere, LABEL_MAX } from "./secretRows";
import { useKindLabel } from "./useKindLabel";
import { useShownCiter } from "./useShownCiter";

interface Props {
  row: SecretRef | null;
  onOpenChange: (open: boolean) => void;
}

const FIELD = "text-xs font-label text-text";

export function EditSecretDialog({ row, onOpenChange }: Props) {
  const notes = useSecretNotes();
  const set = useSetSecret();
  const pending = notes.isPending || set.isPending;
  return (
    <Dialog open={row !== null} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-[480px]">
        {/* Mounted on each open, so the fields start from the secret as it is now. */}
        {row ? (
          <EditSecretForm row={row} notes={notes} set={set} onDone={() => onOpenChange(false)} />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

interface FormProps {
  row: SecretRef;
  notes: ReturnType<typeof useSecretNotes>;
  set: ReturnType<typeof useSetSecret>;
  onDone: () => void;
}

function EditSecretForm({ row, notes, set, onDone }: FormProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const kindLabel = useKindLabel();
  const shown = useShownCiter();
  const labelId = useId();
  const descriptionId = useId();
  const valueId = useId();
  const [label, setLabel] = useState(row.label ?? "");
  const [description, setDescription] = useState(row.description ?? "");
  const [value, setValue] = useState("");

  const { reset: resetNotes } = notes;
  const { reset: resetSet } = set;
  useEffect(() => {
    resetNotes();
    resetSet();
  }, [resetNotes, resetSet]);

  const name = displayName(row, t("secrets.unnamed"));
  const citers = citersOf(row).map(shown);
  const storing = isMissingHere(row);
  const pending = notes.isPending || set.isPending;

  const changed: { label?: string; description?: string } = {};
  if (label.trim() !== (row.label ?? "")) changed.label = label.trim();
  if (description.trim() !== (row.description ?? "")) changed.description = description.trim();
  const notesChanged = Object.keys(changed).length > 0;
  const canSubmit = (notesChanged || value !== "") && !pending;

  const submit = async () => {
    if (!canSubmit) return;
    try {
      if (notesChanged) await notes.mutateAsync({ ref: row.ref, ...changed });
      if (value) await set.mutateAsync({ ref: row.ref, value });
      const saved = changed.label ? changed.label : name;
      toast.success(
        value && !notesChanged
          ? t(storing ? "secrets.replace.stored" : "secrets.replace.replaced", { name: saved })
          : t("secrets.edit.saved", { name: saved }),
      );
      onDone();
    } catch {
      // Shown inline from the mutation's error.
    }
  };

  const error = notes.error ?? set.error;
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <DialogHeader>
        <DialogTitle>{t("secrets.edit.title", { name })}</DialogTitle>
        <DialogDescription className="sr-only">{t("secrets.edit.body")}</DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={labelId} className={FIELD}>
          {t("secrets.add.label")}
        </label>
        <Input
          id={labelId}
          value={label}
          maxLength={LABEL_MAX}
          autoComplete="off"
          autoFocus
          placeholder={name}
          onChange={(e) => setLabel(e.target.value)}
        />
        <p className="text-xs text-text-muted">{t("secrets.edit.labelHint")}</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={descriptionId} className={FIELD}>
          {t("secrets.detail.description")}
        </label>
        <Input
          id={descriptionId}
          value={description}
          maxLength={DESCRIPTION_MAX}
          autoComplete="off"
          placeholder={t("secrets.detail.descriptionPlaceholder")}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={valueId} className={FIELD}>
          {t(storing ? "secrets.add.value" : "secrets.replace.value")}
        </label>
        <PasswordInput
          id={valueId}
          value={value}
          autoComplete="off"
          placeholder={storing ? undefined : t("secrets.edit.valuePlaceholder")}
          onChange={(e) => setValue(e.target.value)}
        />
        <p className="text-xs text-text-muted">
          {storing ? t("secrets.edit.storeHint") : t("secrets.replace.hint")}
          {citers.length === 0
            ? null
            : ` ${t("secrets.edit.usedBy", {
                citers: citers.map((c) => `${kindLabel(c.kind)} ${c.name}`).join(", "),
              })}`}
        </p>
      </div>
      {error ? (
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, error)}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={!canSubmit}>
          {pending ? t("secrets.replace.submitting") : t("common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}
