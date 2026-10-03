// src/components/chat/ConversationsBulkBar.tsx — the Conversations table's
// selection bar, which takes the filter bar's place while rows are ticked:
// "N selected", then Archive (Unarchive in the archived view) and Delete, then
// Clear. Delete asks first, naming how many go and the first few titles; the
// other runs straight away and answers with a toast.
import { useState } from "react";
import { Archive, ArchiveRestore, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { BulkBar } from "@/components/DataTableSelection";
import { TableActionButton } from "@/components/table/TableActionButton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { Conversation } from "@/lib/api/chat";
import { useConversationBatch } from "@/lib/hooks/useConversationBatch";

const TITLES_SHOWN = 3;

interface Props {
  selected: Conversation[];
  archivedView: boolean;
  /** Drops the selection (after a run that finished, or on Clear). */
  onClear: () => void;
}

export function ConversationsBulkBar({ selected, archivedView, onClear }: Props) {
  const { t } = useTranslation();
  const batch = useConversationBatch();
  const [confirming, setConfirming] = useState(false);
  const ids = selected.map((c) => c.id);
  const titles = selected.slice(0, TITLES_SHOWN).map((c) => `“${c.title}”`);
  const more = selected.length - titles.length;

  const move = async () => {
    await batch.run(archivedView ? "unarchive" : "archive", ids);
    onClear();
  };
  const remove = async () => {
    await batch.run("delete", ids);
    setConfirming(false);
    onClear();
  };

  return (
    <div role="region" aria-label={t("conversations.bulk.label")} aria-busy={batch.isPending}>
      <BulkBar
        label={t("conversations.bulk.selected", { count: selected.length })}
        clearLabel={t("common.clear")}
        onClear={onClear}
      >
        <TableActionButton
          icon={archivedView ? ArchiveRestore : Archive}
          label={
            archivedView ? t("conversations.history.unarchive") : t("conversations.history.archive")
          }
          disabled={batch.isPending}
          onClick={() => void move()}
        />
        <TableActionButton
          icon={Trash2}
          label={t("common.delete")}
          destructive
          disabled={batch.isPending}
          onClick={() => setConfirming(true)}
        />
      </BulkBar>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("conversations.bulk.deleteTitle", { count: selected.length })}
        description={t("conversations.bulk.deleteBody", {
          titles:
            titles.join(", ") + (more > 0 ? t("conversations.bulk.andMore", { count: more }) : ""),
        })}
        confirmLabel={t("common.delete")}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteSelected")}
        pending={batch.isPending}
        onConfirm={remove}
      />
    </div>
  );
}
