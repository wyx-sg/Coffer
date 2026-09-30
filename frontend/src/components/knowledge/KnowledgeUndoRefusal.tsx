// frontend/src/components/knowledge/KnowledgeUndoRefusal.tsx
//
// The note a refused Undo this pass leaves above the pass's documents (spec
// knowledge "Keep every document's history and undo a pass as a whole"): the
// document edited since is named, nothing was written, and a single document
// can still be restored from its History. When the daemon sends the prompt for
// undoing the pass by hand — reversing it while keeping the later edits — it
// is offered to the person's agent beside the note.
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";

interface Props {
  /** The refusal in words (`undoRefusal`). */
  text: string;
  /** The backend's hand-off for undoing the pass by hand, when it sent one. */
  handoff: string | null;
}

export function KnowledgeUndoRefusal({ text, handoff }: Props) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2.5"
    >
      <AlertTriangle className="mt-px size-3.5 shrink-0 text-warning" aria-hidden />
      <div className="flex flex-col gap-[3px]">
        <p className="text-sm font-label">{t("knowledge.pass.undoRefusedTitle")}</p>
        <p className="text-xs leading-[1.45] text-text-muted">{text}</p>
        {handoff ? (
          <div className="mt-1.5">
            <AgentHandoff prompt={handoff} size="sm" />
          </div>
        ) : null}
      </div>
    </div>
  );
}
