// src/components/secret/AddValuesDialog.tsx — add a value for each secret this Mac has none for, in one dialog.
//
// One row per missing secret (its name and what uses it, a password field); a row left empty
// stays missing, and Save N values stores only the filled rows, one PUT each. A value that waits
// for approval (202) is stored sealed and the toast says so. A row that failed keeps its text and
// shows why; the dialog closes once every filled row is stored.
import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
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
import { joinNames } from "@/lib/skills/names";
import { citersOf, shortName } from "./secretRows";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The secrets this Mac has no value for. */
  rows: SecretRef[];
}

export function AddValuesDialog({ open, onOpenChange, rows }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const set = useSetSecret();
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setValues({});
    setErrors({});
  }, [open]);

  const filled = rows.filter((r) => (values[r.ref] ?? "") !== "");

  const save = async () => {
    if (filled.length === 0 || saving) return;
    setSaving(true);
    const failed: Record<string, string> = {};
    let stored = 0;
    for (const row of filled) {
      try {
        await set.mutateAsync({ ref: row.ref, value: values[row.ref] });
        stored += 1;
        setValues((prev) => ({ ...prev, [row.ref]: "" }));
      } catch (e) {
        failed[row.ref] = translateApiError(t, e);
      }
    }
    setSaving(false);
    setErrors(failed);
    if (stored > 0) {
      toast.success(t("secrets.addValues.saved", { count: stored }));
    }
    if (Object.keys(failed).length === 0) onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent className="max-w-[640px]">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("secrets.addValues.title")}</DialogTitle>
            <DialogDescription>{t("secrets.addValues.body")}</DialogDescription>
          </DialogHeader>
          <ul className="max-h-[360px] divide-y divide-border-subtle overflow-y-auto rounded-lg border border-border-subtle">
            {rows.map((row) => {
              const name = shortName(row);
              const users = citersOf(row).map((c) => c.name);
              return (
                <li
                  key={row.ref}
                  className="grid grid-cols-[minmax(0,1fr)_240px] items-center gap-3 px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate font-mono text-xs text-text">{name}</p>
                    {users.length > 0 ? (
                      <p className="truncate text-xs text-text-muted">
                        {t("secrets.addValues.usedBy", { names: joinNames(users, i18n.language) })}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-col gap-1">
                    <PasswordInput
                      value={values[row.ref] ?? ""}
                      autoComplete="off"
                      placeholder={t("secrets.addValues.placeholder")}
                      aria-label={t("secrets.addValues.valueFor", { name })}
                      aria-invalid={Boolean(errors[row.ref])}
                      onChange={(e) =>
                        setValues((prev) => ({ ...prev, [row.ref]: e.target.value }))
                      }
                    />
                    {errors[row.ref] ? (
                      <p role="alert" className="text-xs text-danger">
                        {errors[row.ref]}
                      </p>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="flex items-center gap-2 rounded-md bg-surface-sunken px-3 py-2 text-xs text-text-muted">
            <Lock className="size-3.5 shrink-0" aria-hidden />
            {t("secrets.addValues.encrypted")}
          </p>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={saving}
              onClick={() => onOpenChange(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={filled.length === 0} loading={saving}>
              {t("secrets.addValues.save", { count: filled.length })}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
