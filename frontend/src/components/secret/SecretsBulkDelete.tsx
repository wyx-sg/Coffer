// src/components/secret/SecretsBulkDelete.tsx — delete the ticked secrets behind one confirmation; only those that may go are deleted.
//
// A secret something uses, or that waits for approval, is skipped: the confirmation names it
// and the button says how many will actually go ("Delete 2 secrets"). Each deletable secret is
// deleted or refused on its own (one summary toast) and the dialog closes when the run has
// settled. With nothing deletable in the selection the trigger is off.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useBulkDeleteSecrets } from "@/lib/hooks/useSecrets";
import { joinNames } from "@/lib/skills/names";
import { isDeletable, type SecretItem } from "./secretListView";

/** How many names the confirmation lists before "and N more". */
const NAMES_SHOWN = 5;

interface Props {
  /** Every ticked secret, deletable or not. */
  items: SecretItem[];
  onDone?: () => void;
}

export function SecretsBulkDelete({ items, onDone }: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const bulk = useBulkDeleteSecrets();
  const going = items.filter(isDeletable);
  const skipped = items.filter((i) => !isDeletable(i));
  const inUse = skipped.filter((i) => !i.row.unreferenced).map((i) => i.short);
  const waiting = skipped.filter((i) => i.row.unreferenced).map((i) => i.short);
  const names = joinNames(
    going.slice(0, NAMES_SHOWN).map((i) => i.short),
    i18n.language,
  );
  const rest = going.length - NAMES_SHOWN;
  const list = (xs: string[]) => joinNames(xs, i18n.language);
  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="danger"
        disabled={going.length === 0}
        title={going.length === 0 ? t("secrets.bulk.nothingToDelete") : undefined}
        onClick={() => setOpen(true)}
      >
        {t("secrets.bulk.delete")}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={t("secrets.bulk.deleteTitle", { count: items.length })}
        description={
          rest > 0
            ? t("secrets.bulk.deleteBodyMore", { names, count: rest })
            : t("secrets.bulk.deleteBody", { names })
        }
        confirmLabel={t("secrets.bulk.deleteConfirm", { count: going.length })}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteSelected")}
        pending={bulk.isPending}
        onConfirm={async () => {
          await bulk.run(going.map((i) => i.row.ref));
          onDone?.();
        }}
      >
        {inUse.length > 0 ? (
          <p className="rounded-lg bg-accent-soft px-3 py-2 text-xs text-text-muted">
            {t("secrets.bulk.skippedInUse", { count: inUse.length, names: list(inUse) })}
          </p>
        ) : null}
        {waiting.length > 0 ? (
          <p className="rounded-lg bg-accent-soft px-3 py-2 text-xs text-text-muted">
            {t("secrets.bulk.skippedWaiting", { count: waiting.length, names: list(waiting) })}
          </p>
        ) : null}
      </ConfirmDialog>
    </>
  );
}
