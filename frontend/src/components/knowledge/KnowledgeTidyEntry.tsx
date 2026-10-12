// frontend/src/components/knowledge/KnowledgeTidyEntry.tsx
//
// A tidy in a collection's Change log (spec knowledge "Record a tidy as one
// change", "Undo a tidy"): one entry naming the agent and its time, its report
// — or that Coffer closed it without one — the pages it touched by title, and
// **Undo this tidy…**. Undo asks first; when a file was edited since, the
// daemon's refusal becomes a second question naming those files by title,
// whose **Undo anyway** sends `force`. A tidy some later change undid reads
// Undone and offers no Undo.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Undo2 } from "lucide-react";

import {
  ChangeEntry,
  ChangeFiles,
  type TitleOf,
} from "@/components/knowledge/KnowledgeChangeParts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import type { ChangeOut } from "@/lib/api/knowledge";
import { useUndoChange } from "@/lib/hooks/useKnowledge";
import { groupDocuments } from "@/lib/knowledge/changeGroups";
import { whenLabel, writerLabel } from "@/lib/knowledge/changes";
import { pathInCollection } from "@/lib/knowledge/routes";

export function KnowledgeTidyEntry({
  change,
  uid,
  titleOf,
  undone,
}: {
  change: ChangeOut;
  uid: string;
  titleOf: TitleOf;
  undone: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const undo = useUndoChange();
  const [asking, setAsking] = useState(false);
  const [conflict, setConflict] = useState<string[] | null>(null);
  const expired = change.status === "expired";

  const run = (force: boolean) =>
    undo.mutateAsync({ version: change.version, force }).then(() => {
      toast.success(t("knowledge.tidyUndo.done"));
    });

  // The first question: a refusal naming files edited since becomes the
  // second question rather than an error.
  const confirmUndo = () =>
    run(false).catch((error: unknown) => {
      if (error instanceof ApiError && error.code === "KNOWLEDGE_UNDO_CONFLICT") {
        const details = error.details as { documents?: string[] } | undefined;
        setConflict(details?.documents ?? []);
        return;
      }
      throw error;
    });

  return (
    <ChangeEntry
      tone="accent"
      heading={
        <span className="flex items-center gap-2">
          {t("knowledge.operation.tidy")}
          {undone ? <Badge variant="secondary">{t("knowledge.tidyUndo.undone")}</Badge> : null}
        </span>
      }
      meta={`${writerLabel(t, change)} · ${whenLabel(t, change.time, i18n.language)}`}
    >
      {expired ? (
        <p className="text-sm text-text-muted">{t("knowledge.changeLog.tidyExpired")}</p>
      ) : (
        <p className="whitespace-pre-line break-words text-sm leading-[1.55] text-text">
          {change.summary}
        </p>
      )}
      <ChangeFiles documents={groupDocuments([change])} uid={uid} titleOf={titleOf} />
      {undone ? null : (
        <div>
          <Button variant="outline" size="sm" onClick={() => setAsking(true)}>
            <Undo2 aria-hidden /> {t("knowledge.tidyUndo.button")}
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title={t("knowledge.tidyUndo.title")}
        description={t("knowledge.tidyUndo.body", { count: change.documents.length })}
        confirmLabel={t("knowledge.tidyUndo.confirm")}
        pendingLabel={t("knowledge.tidyUndo.pending")}
        errorTitle={t("knowledge.tidyUndo.failed")}
        onConfirm={confirmUndo}
      />
      <ConfirmDialog
        open={conflict !== null}
        onOpenChange={(open) => {
          if (!open) setConflict(null);
        }}
        title={t("knowledge.tidyUndo.conflictTitle")}
        description={t("knowledge.tidyUndo.conflictBody", { count: conflict?.length ?? 0 })}
        confirmLabel={t("knowledge.tidyUndo.anyway")}
        pendingLabel={t("knowledge.tidyUndo.pending")}
        errorTitle={t("knowledge.tidyUndo.failed")}
        onConfirm={() => run(true)}
      >
        <ul className="flex flex-col gap-0.5 rounded-lg bg-surface-sunken px-3 py-2">
          {(conflict ?? []).map((path) => (
            <li key={path} className="truncate text-sm" title={pathInCollection(path)}>
              {titleOf(path)}
            </li>
          ))}
        </ul>
      </ConfirmDialog>
    </ChangeEntry>
  );
}
