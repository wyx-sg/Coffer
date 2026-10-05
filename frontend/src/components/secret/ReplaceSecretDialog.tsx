// src/components/secret/ReplaceSecretDialog.tsx — Replace value (or, for a secret missing on this Mac, Add value).
//
// Names the secret and what uses it, takes the new value without ever
// showing the old one, and says the old value is destroyed. The value is stored
// at once (spec secret "Store a secret through the API"). A secret missing on this
// Mac — cited but not stored, or stored under another Mac's master key — gets
// its value here too (spec secret "Show a secret this Mac cannot open as
// missing on this Mac").
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
import { PasswordInput } from "@/components/ui/password-input";
import { useToast } from "@/components/ui/toast";
import type { SecretRef } from "@/lib/api/secret";
import { translateApiError } from "@/lib/api/errors";
import { useSetSecret } from "@/lib/hooks/useSecrets";
import { citersOf, displayName, isMissingHere } from "./secretRows";
import { useKindLabel } from "./useKindLabel";
import { useShownCiter } from "./useShownCiter";

interface Props {
  row: SecretRef | null;
  onOpenChange: (open: boolean) => void;
}

const TERM = "text-xs text-text-muted";

export function ReplaceSecretDialog({ row, onOpenChange }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const kindLabel = useKindLabel();
  const shown = useShownCiter();
  const set = useSetSecret();
  const valueId = useId();
  const [value, setValue] = useState("");
  const open = row !== null;

  const { reset } = set;
  useEffect(() => {
    if (!open) return;
    setValue("");
    reset();
  }, [open, reset]);

  if (!row) return null;
  const name = displayName(row, t("secrets.unnamed"));
  const citers = citersOf(row).map(shown);
  const storing = isMissingHere(row);

  const submit = async () => {
    if (!value || set.isPending) return;
    try {
      await set.mutateAsync({ ref: row.ref, value });
      toast.success(t(storing ? "secrets.replace.stored" : "secrets.replace.replaced", { name }));
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
            void submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {t(storing ? "secrets.replace.storeTitle" : "secrets.replace.title", { name })}
            </DialogTitle>
            <DialogDescription className="sr-only">{t("secrets.replace.hint")}</DialogDescription>
          </DialogHeader>
          <dl className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-1.5">
            <dt className={TERM}>{t("secrets.cols.usedBy")}</dt>
            <dd className="text-xs text-text">
              {citers.length === 0
                ? t("secrets.usedBy.nothing")
                : citers.map((c) => `${kindLabel(c.kind)} ${c.name}`).join(", ")}
            </dd>
          </dl>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={valueId} className="text-xs font-label text-text">
              {t("secrets.replace.value")}
            </label>
            <PasswordInput
              id={valueId}
              value={value}
              autoComplete="off"
              autoFocus
              onChange={(e) => setValue(e.target.value)}
            />
            {storing ? null : (
              <p className="text-xs text-text-muted">{t("secrets.replace.hint")}</p>
            )}
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
            <Button type="submit" disabled={!value || set.isPending}>
              {set.isPending
                ? t("secrets.replace.submitting")
                : t(storing ? "secrets.replace.storeSubmit" : "secrets.replace.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
