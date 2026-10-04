// frontend/src/components/knowledge/KnowledgeUndoRefusal.tsx
//
// The notice a refused Undo this pass leaves above the pass's documents (board
// 5.1.20; spec knowledge "Keep every document's history and undo a pass as a
// whole"): one sentence naming the document changed since — nothing was
// written — and a button to that document's History, where a single version
// can still be restored. No hand-off: the way out is the History.
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";

interface Props {
  /** The refusal in words (`undoRefusal`). */
  text: string;
  /** The changed document's History; null when the daemon named no document. */
  historyTo: string | null;
}

export function KnowledgeUndoRefusal({ text, historyTo }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2.5"
    >
      <AlertTriangle className="mt-px size-3.5 shrink-0 text-warning" aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
        <p className="text-sm font-label">{t("knowledge.pass.undoRefusedTitle")}</p>
        <p className="text-xs leading-[1.45] text-text-muted">{text}</p>
      </div>
      {historyTo ? (
        <Button variant="outline" size="sm" onClick={() => navigate(historyTo)}>
          {t("knowledge.pass.openHistory")}
        </Button>
      ) : null}
    </div>
  );
}
