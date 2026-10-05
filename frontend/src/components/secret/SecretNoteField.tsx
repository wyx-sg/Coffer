// src/components/secret/SecretNoteField.tsx — a secret's label or description, edited in place.
//
// Leaving the field or pressing Enter saves; an empty value removes the note; the reference never
// changes (spec secret "Label and describe a secret without changing its reference"). A failure
// is shown under the field. `placeholder` is what the field reads while empty.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import type { SecretRef } from "@/lib/api/secret";
import { useSecretNotes } from "@/lib/hooks/useSecrets";
import { cn } from "@/lib/utils";
import { DESCRIPTION_MAX, LABEL_MAX } from "./secretRows";

interface Props {
  row: SecretRef;
  field: "label" | "description";
  placeholder: string;
  className?: string;
}

export function SecretNoteField({ row, field, placeholder, className }: Props) {
  const { t } = useTranslation();
  const notes = useSecretNotes();
  const errorId = useId();
  const saved = row[field] ?? "";
  const [draft, setDraft] = useState(saved);
  useEffect(() => setDraft(saved), [saved, row.ref]);

  const save = () => {
    const next = draft.trim();
    if (next === saved || notes.isPending) return;
    notes.mutate({ ref: row.ref, [field]: next });
  };
  return (
    <div className="min-w-0">
      <Input
        value={draft}
        aria-label={t(`secrets.detail.${field}`)}
        aria-describedby={notes.error ? errorId : undefined}
        maxLength={field === "label" ? LABEL_MAX : DESCRIPTION_MAX}
        autoComplete="off"
        placeholder={placeholder}
        className={cn(
          "h-auto border-transparent bg-transparent px-1.5 shadow-none hover:border-border focus-visible:bg-surface",
          className,
        )}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.currentTarget.blur();
          }
        }}
      />
      {notes.error ? (
        <p id={errorId} role="alert" className="px-1.5 pt-1 text-xs text-danger">
          {translateApiError(t, notes.error)}
        </p>
      ) : null}
    </div>
  );
}
