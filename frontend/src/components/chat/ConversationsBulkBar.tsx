// src/components/chat/ConversationsBulkBar.tsx — the Conversations list's
// selection bar, which takes the filter row's place while rows are ticked:
// "3 of 8 selected", then Archive (Unarchive in the archived view), Delete…
// and Clear. Delete asks first, listing the titles that go; Archive runs
// straight away and answers with a toast that has Undo.
import { useState } from "react";
import { Archive, ArchiveRestore, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { TableActionButton } from "@/components/table/TableActionButton";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { Conversation } from "@/lib/api/chat";
import { useConversationBatch } from "@/lib/hooks/useConversationBatch";

/** Titles listed in the delete confirmation before "Show all". */
const TITLES_SHOWN = 5;

interface Props {
  selected: Conversation[];
  /** How many conversations the current view holds (the server's count). */
  total: number;
  archivedView: boolean;
  /** Drops the selection (after a run that finished, or on Clear). */
  onClear: () => void;
}

export function ConversationsBulkBar({ selected, total, archivedView, onClear }: Props) {
  const { t } = useTranslation();
  const batch = useConversationBatch();
  const [confirming, setConfirming] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const ids = selected.map((c) => c.id);
  const shown = showAll ? selected : selected.slice(0, TITLES_SHOWN);

  const move = async () => {
    await batch.run(archivedView ? "unarchive" : "archive", ids);
    onClear();
  };
  const remove = async () => {
    await batch.run("delete", ids);
    setConfirming(false);
    onClear();
  };
  const open = (next: boolean) => {
    setConfirming(next);
    if (!next) setShowAll(false);
  };

  return (
    <div role="region" aria-label={t("conversations.bulk.label")} aria-busy={batch.isPending}>
      {/* Foundations-Tables "Bulk bar": a 40px raised strip, r10. */}
      <div className="flex min-h-10 flex-wrap items-center gap-2 rounded-xl bg-surface-raised py-[7px] pl-3 pr-2 shadow-overlay">
        <span className="mr-2 text-sm font-label text-text">
          {t("conversations.bulk.selected", { count: selected.length, total })}
        </span>
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
          label={t("conversations.history.delete")}
          destructive
          disabled={batch.isPending}
          onClick={() => open(true)}
        />
        <Button variant="ghost" size="sm" onClick={onClear}>
          {t("common.clear")}
        </Button>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={open}
        title={t("conversations.bulk.deleteTitle", { count: selected.length })}
        description={t("conversations.bulk.deleteBody")}
        confirmLabel={t("conversations.bulk.deleteConfirm", { count: selected.length })}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteSelected")}
        pending={batch.isPending}
        onConfirm={remove}
      >
        <ul className="m-0 max-h-48 list-none overflow-y-auto rounded-lg border border-border-subtle p-0">
          {shown.map((c) => (
            <li
              key={c.id}
              className="truncate border-t border-border-subtle px-3 py-1.5 text-sm text-text first:border-t-0"
            >
              {c.title}
            </li>
          ))}
        </ul>
        {selected.length > TITLES_SHOWN && !showAll ? (
          <p className="m-0 flex items-center gap-1 text-xs text-text-muted">
            {t("conversations.bulk.showing", { shown: TITLES_SHOWN, count: selected.length })}
            <span aria-hidden>·</span>
            <button
              type="button"
              className="text-accent-text underline-offset-2 hover:underline"
              onClick={() => setShowAll(true)}
            >
              {t("conversations.bulk.showAll")}
            </button>
          </p>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}
