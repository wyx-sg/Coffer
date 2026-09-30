// src/components/credentials/DeleteSecretDialog.tsx — Delete a secret nothing uses, or say what still uses it.
//
// A secret something cites opens straight into the refusal: each citer by
// kind and name with a link to its page, and Delete disabled. One nothing
// cites is confirmed and deleted. Something may have started citing it since
// the page loaded: the daemon then refuses with `409 CREDENTIAL_IN_USE` naming
// each citer, and the dialog turns into that same refusal — while the row
// stays listed (spec credentials "Refuse to delete a credential still in use").
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
import { useToast } from "@/components/ui/toast";
import type { CredentialRef } from "@/lib/api/credentials";
import { ApiError } from "@/lib/api/errors";
import { useDeleteSecret } from "@/lib/hooks/useSecrets";
import { citersFromRefusal, citersOf, displayName, referenceOf, type Citer } from "./secretRows";
import { useKindLabel } from "./useKindLabel";

interface Props {
  row: CredentialRef | null;
  onOpenChange: (open: boolean) => void;
}

function InUse({
  row,
  citers,
  onClose,
}: {
  row: CredentialRef;
  citers: Citer[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("secrets.blocked.title", { name: displayName(row) })}</DialogTitle>
        <DialogDescription>
          {t("secrets.blocked.body", { count: citers.length, reference: referenceOf(row) })}
        </DialogDescription>
      </DialogHeader>
      <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
        {citers.map((c) => (
          <li key={c.key} className="flex items-center gap-3 px-3 py-2">
            <span className="min-w-0 flex-1 truncate text-sm text-text">{c.name}</span>
            <span className="text-xs text-text-muted">{kindLabel(c.kind)}</span>
            {c.href ? (
              <Button asChild variant="outline" size="sm">
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
        <Button variant="destructive" disabled>
          {t("secrets.delete.submit")}
        </Button>
      </DialogFooter>
    </>
  );
}

export function DeleteSecretDialog({ row, onOpenChange }: Props) {
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
  const name = displayName(row);
  const close = () => onOpenChange(false);
  const known = citersOf(row);
  const blocked = refused ?? (known.length > 0 ? known : null);

  if (blocked) {
    return (
      <Dialog open onOpenChange={onOpenChange}>
        <DialogContent className="max-w-[460px]">
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
    } catch (e) {
      if (e instanceof ApiError && e.code === "CREDENTIAL_IN_USE") {
        setRefused(citersFromRefusal(e.details));
      }
      // Any other failure stays in the dialog, from the mutation's error.
    }
  };
  const inUseError = remove.error instanceof ApiError && remove.error.code === "CREDENTIAL_IN_USE";

  return (
    <ConfirmDialog
      open
      onOpenChange={(next) => !remove.isPending && onOpenChange(next)}
      title={t("secrets.delete.title", { name })}
      description={t("secrets.delete.body")}
      confirmLabel={remove.isPending ? t("secrets.delete.submitting") : t("secrets.delete.submit")}
      pending={remove.isPending}
      error={inUseError ? undefined : (remove.error ?? undefined)}
      onConfirm={() => void confirm()}
    >
      <dl className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 text-xs">
        <dt className="text-text-muted">{t("secrets.replace.secret")}</dt>
        <dd className="truncate font-mono text-text">{name}</dd>
      </dl>
    </ConfirmDialog>
  );
}
