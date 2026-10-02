// src/components/secret/SecretsBulkDelete.tsx — delete several secrets behind one confirmation; each is deleted or refused on its own.
//
// Used by the selection bar's Delete and by the filter row's "Delete unused…". The confirmation
// says how many and names the first few; the run settles every secret (one summary toast) and
// the dialog closes when it has. The caller passes only secrets that may go.
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { TableActionButton } from "@/components/table/TableActionButton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useBulkDeleteSecrets } from "@/lib/hooks/useSecrets";
import { joinNames } from "@/lib/skills/names";
import type { SecretItem } from "./secretListView";

/** How many names the confirmation lists before "and N more". */
const NAMES_SHOWN = 5;

interface Props {
  items: SecretItem[];
  /** The trigger's label ("Delete", "Delete unused…"). */
  label: string;
  /** Why the trigger is off, when it is. */
  disabledReason?: string;
  onDone?: () => void;
}

export function SecretsBulkDelete({ items, label, disabledReason, onDone }: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const bulk = useBulkDeleteSecrets();
  const names = joinNames(
    items.slice(0, NAMES_SHOWN).map((i) => i.short),
    i18n.language,
  );
  const rest = items.length - NAMES_SHOWN;
  return (
    <>
      <TableActionButton
        icon={Trash2}
        label={label}
        destructive
        disabled={Boolean(disabledReason) || items.length === 0}
        title={disabledReason}
        onClick={() => setOpen(true)}
      />
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={t("secrets.bulk.deleteTitle", { count: items.length })}
        description={
          rest > 0
            ? t("secrets.bulk.deleteBodyMore", { names, count: rest })
            : t("secrets.bulk.deleteBody", { names })
        }
        confirmLabel={t("secrets.bulk.deleteConfirm", { count: items.length })}
        pending={bulk.isPending}
        onConfirm={async () => {
          await bulk.run(items.map((i) => i.row.ref));
          onDone?.();
        }}
      />
    </>
  );
}
