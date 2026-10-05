// src/components/secret/DeleteSecretDialog.tsx — Delete a secret nothing uses, or say what still uses it.
//
// A secret something cites opens straight into the refusal: each citer by
// kind and name with a link to its page, and only Close. One nothing
// cites is confirmed and deleted. Something may have started citing it since
// the page loaded: the daemon then refuses with `409 SECRET_IN_USE` naming
// each citer, and the dialog turns into that same refusal — while the row
// stays listed (spec secret "Refuse to delete a secret still in use").
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RelativeTime } from "@/components/RelativeTime";
import { useToast } from "@/components/ui/toast";
import type { SecretRef } from "@/lib/api/secret";
import { ApiError } from "@/lib/api/errors";
import { useDeleteSecret } from "@/lib/hooks/useSecrets";
import { useKindPageOpen } from "@/lib/hooks/useFeatures";
import { citersFromRefusal, citersOf, displayName, referenceOf, type Citer } from "./secretRows";
import { useKindLabel } from "./useKindLabel";

interface Props {
  row: SecretRef | null;
  onOpenChange: (open: boolean) => void;
  /** The secret is gone: the page leaves its detail. */
  onDeleted?: () => void;
}

function InUse({ row, citers, onClose }: { row: SecretRef; citers: Citer[]; onClose: () => void }) {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  const pageOpen = useKindPageOpen();
  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {t("secrets.blocked.title", { name: displayName(row, t("secrets.unnamed")) })}
        </DialogTitle>
        <DialogDescription>
          {t("secrets.blocked.body", { count: citers.length, reference: referenceOf(row) })}
        </DialogDescription>
      </DialogHeader>
      <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
        {citers.map((c) => (
          <li key={c.key} className="flex items-center gap-3 px-3 py-2">
            <span className="min-w-0 flex-1 truncate text-sm text-text">{c.name}</span>
            <span className="text-xs text-text-muted">{kindLabel(c.kind)}</span>
            {c.href && pageOpen(c.kind) ? (
              <Button asChild variant="ghost" size="sm">
                <Link to={c.href} onClick={onClose}>
                  {t("secrets.blocked.open")}
                </Link>
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          {t("common.close")}
        </Button>
      </DialogFooter>
    </>
  );
}

export function DeleteSecretDialog({ row, onOpenChange, onDeleted }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const remove = useDeleteSecret();
  const [refused, setRefused] = useState<Citer[] | null>(null);
  const open = row !== null;

  const { reset } = remove;
  useEffect(() => {
    if (!open) return;
    setRefused(null);
    reset();
  }, [open, reset]);

  if (!row) return null;
  const name = displayName(row, t("secrets.unnamed"));
  const close = () => onOpenChange(false);
  const known = citersOf(row);
  const blocked = refused ?? (known.length > 0 ? known : null);

  if (blocked) {
    return (
      <Dialog open onOpenChange={onOpenChange}>
        <DialogContent className="max-w-[420px]">
          <InUse row={row} citers={blocked} onClose={close} />
        </DialogContent>
      </Dialog>
    );
  }

  const confirm = async () => {
    try {
      await remove.mutateAsync(row.ref);
      toast.success(t("secrets.delete.deleted", { name }));
      close();
      onDeleted?.();
    } catch (e) {
      if (e instanceof ApiError && e.code === "SECRET_IN_USE") {
        setRefused(citersFromRefusal(e.details));
      }
      // Any other failure stays in the dialog, from the mutation's error.
    }
  };
  const inUseError = remove.error instanceof ApiError && remove.error.code === "SECRET_IN_USE";

  return (
    <ConfirmDialog
      open
      onOpenChange={(next) => !remove.isPending && onOpenChange(next)}
      title={t("secrets.delete.title", { name })}
      description={t("secrets.delete.body")}
      confirmLabel={t("secrets.delete.submit")}
      pendingLabel={t("secrets.delete.submitting")}
      errorTitle={t("common.couldntDelete", { name: name })}
      pending={remove.isPending}
      error={inUseError ? undefined : (remove.error ?? undefined)}
      onConfirm={() => void confirm()}
    >
      <dl className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        <dt className="text-text-muted">{t("secrets.cols.lastUsed")}</dt>
        <dd className="text-text">
          {row.last_used_at ? <RelativeTime iso={row.last_used_at} /> : t("secrets.time.never")}
        </dd>
      </dl>
    </ConfirmDialog>
  );
}
