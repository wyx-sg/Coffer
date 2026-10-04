// frontend/src/components/knowledge/KnowledgeUndoPassDialog.tsx
//
// Undo this pass — asked first, then the whole pass at once (board 5.1.19; spec
// knowledge "Keep every document's history and undo a pass as a whole"): every
// document it changed goes back to how it was before, each as a new version by
// you, and the inbox items it curated are not queued again. All or nothing:
// when a document it wrote has changed since, the daemon refuses the whole
// undo and writes nothing. The dialog then closes and the pass's page says so,
// naming that document and opening its History (KnowledgeUndoRefusal;
// KnowledgeChangeView reads the refusal off the same mutation). It is the 420
// ConfirmDialog; its one sentence is the all-or-nothing rule.
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { ChangeOut } from "@/lib/api/knowledge";
import type { useUndoPass } from "@/lib/hooks/useKnowledgeHistory";
import { useToast } from "@/components/ui/toast";
import { whenLabel } from "@/lib/knowledge/changes";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  change: ChangeOut;
  undo: ReturnType<typeof useUndoPass>;
}

const SIGN = { added: "−", modified: "~", removed: "+" } as const;

export function KnowledgeUndoPassDialog({ open, onOpenChange, change, undo }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const time = new Date(change.time).toLocaleTimeString(i18n.language, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("knowledge.pass.undoTitle")}
      description={t("knowledge.pass.undoBody", { when: time })}
      confirmLabel={undo.isPending ? t("knowledge.pass.undoing") : t("knowledge.pass.undoConfirm")}
      pending={undo.isPending}
      onConfirm={() => {
        undo.reset();
        undo.mutate(change.version, {
          onSuccess: () => {
            onOpenChange(false);
            toast.success(t("knowledge.pass.undoneToast"));
          },
          // The refusal is the pass page's to show; the dialog steps aside.
          onError: () => onOpenChange(false),
        });
      }}
    >
      <ul className="flex flex-col gap-1.5 text-sm">
        {change.documents.map((d) => (
          <li key={d.path} className="flex items-baseline gap-2">
            <span
              className={cn(
                "w-3 shrink-0 font-mono text-xs",
                d.status === "added" ? "text-danger" : "text-text-subtle",
              )}
              aria-hidden
            >
              {SIGN[d.status]}
            </span>
            <span className="min-w-0 truncate font-mono text-xs">{d.path}</span>
            <span className="ml-auto shrink-0 text-xs text-text-subtle">
              {t(`knowledge.pass.undoEffect.${d.status}`, {
                when: whenLabel(t, change.time, i18n.language),
              })}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-sm text-text-muted">{t("knowledge.pass.undoNote")}</p>
    </ConfirmDialog>
  );
}
