// frontend/src/components/knowledge/KnowledgeUndoPassDialog.tsx
//
// Undo this pass — asked first, then the whole pass at once (spec knowledge
// "Keep every document's history and undo a pass as a whole"): every document
// it changed goes back to how it was before, each as a new version by you, and
// the inbox items it curated are not queued again. When a document it wrote
// has changed since, the daemon refuses the whole undo and writes nothing; the
// dialog stays open and names that document.
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { ChangeOut } from "@/lib/api/knowledge";
import { useUndoPass } from "@/lib/hooks/useKnowledgeHistory";
import { useToast } from "@/components/ui/toast";
import { formatDateTime } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  change: ChangeOut;
}

/** The refusal in words: which document changed since, when the daemon names it. */
function refusalText(t: TFunction, error: unknown): string {
  if (error instanceof ApiError && error.code === "KNOWLEDGE_UNDO_CONFLICT") {
    const document = (error.details as { document?: unknown } | undefined)?.document;
    if (typeof document === "string") return t("knowledge.pass.undoRefused", { document });
  }
  return translateApiError(t, error);
}

export function KnowledgeUndoPassDialog({ open, onOpenChange, change }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const undo = useUndoPass();

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) undo.reset();
      }}
      title={t("knowledge.pass.undoTitle")}
      description={t("knowledge.pass.undoBody", { when: formatDateTime(change.time) })}
      confirmLabel={undo.isPending ? t("knowledge.pass.undoing") : t("knowledge.pass.undoConfirm")}
      pending={undo.isPending}
      onConfirm={() =>
        undo.mutate(change.version, {
          onSuccess: () => {
            onOpenChange(false);
            toast.success(t("knowledge.pass.undoneToast"));
          },
        })
      }
    >
      <ul className="space-y-1 text-sm">
        {change.documents.map((d) => (
          <li key={d.path} className="flex items-baseline gap-2">
            <span className="font-mono text-xs">{d.path}</span>
            <span className="text-xs text-text-subtle">
              {t(`knowledge.pass.undoEffect.${d.status}`)}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-text-subtle">{t("knowledge.pass.undoNote")}</p>
      {undo.error ? (
        <p role="alert" className="text-sm text-danger">
          {refusalText(t, undo.error)}
        </p>
      ) : null}
    </ConfirmDialog>
  );
}
