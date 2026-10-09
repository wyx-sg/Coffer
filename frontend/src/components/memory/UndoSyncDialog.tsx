// frontend/src/components/memory/UndoSyncDialog.tsx
//
// Undo sync… (spec memory "Undo sync"): the confirmation names what it removes
// from this machine's agents — every copy Coffer wrote that the agent has not
// changed (counted per agent), the Coffer block in each project's MEMORY.md,
// Claude Code's rules file and Codex's extension folder — that automatic sync
// turns off, and what it keeps: the hub in the vault, every memory an agent
// wrote itself and every copy an agent edited. It closes only once the undo
// succeeded; a failure stays in the dialog.
import { Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { sortAgents } from "@/components/agent/agentOrder";
import { ConfirmDialog, ConfirmFacts } from "@/components/ui/confirm-dialog";
import { agentTypeLabel } from "@/lib/agents/display";
import type { SyncAgent } from "@/lib/api/memoryTypes";
import { useUndoSync } from "@/lib/hooks/useMemory";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: readonly SyncAgent[];
}

export function UndoSyncDialog({ open, onOpenChange, agents }: Props) {
  const { t } = useTranslation();
  const undo = useUndoSync();
  const copies = sortAgents(agents.map((a) => ({ ...a, type: a.agent_type })))
    .map((a) =>
      t("memory.undo.copiesIn", { count: a.copies.written ?? 0, agent: agentTypeLabel(a.type) }),
    )
    .join(" · ");

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("memory.undo.title")}
      description={t("memory.undo.description")}
      confirmLabel={t("memory.undo.confirm")}
      confirmIcon={<Undo2 aria-hidden />}
      pendingLabel={t("memory.undo.pending")}
      variant="destructive"
      width="wide"
      errorTitle={t("memory.undo.failed")}
      onConfirm={() => undo.mutateAsync()}
    >
      <ConfirmFacts
        items={[
          {
            label: t("memory.undo.removes"),
            value: (
              <span className="flex flex-col gap-0.5">
                <span>{copies || t("memory.undo.noCopies")}</span>
                <span className="text-xs text-text-muted">{t("memory.undo.files")}</span>
              </span>
            ),
          },
          { label: t("memory.undo.turnsOff"), value: t("memory.undo.automatic") },
          { label: t("memory.undo.keeps"), value: t("memory.undo.kept") },
        ]}
      />
    </ConfirmDialog>
  );
}
