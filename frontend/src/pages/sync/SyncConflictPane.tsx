// frontend/src/pages/sync/SyncConflictPane.tsx
//
// The right pane of Resolve conflicts, for one file: its path and who changed
// it when, Open in editor and Hand off to <Agent> (for this one file), and then one of
// three states — the two choices (6.4.06), the editor (6.4.07) or an agent's
// merge to check (6.4.34). An encrypted secret (`secret/*.enc`) is only ever
// answered by one of the two choices — no editor, no agent, and its contents
// are never shown.
//
// Open in editor asks the daemon for the marked-up copy and has the OS open
// it; the pane then waits for Mark resolved, which answers `edited` from the
// copy as saved (SyncConflictCopyCard, which then carries Open in editor too).
// Whether the editing state shows is the page's own, because the copy exists as
// soon as an agent was handed the file.
import { ExternalLink, MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import type { ConflictFile } from "@/lib/api/sync";
import { SyncConflictChoices } from "./SyncConflictChoices";
import { SyncConflictCopyCard } from "./SyncConflictCopyCard";
import { areaLabel, canAskAgent, clock, otherMachine } from "./syncConflictFormat";
import type { ResolveSource } from "./useResolveSource";

interface Props {
  file: ConflictFile;
  source: ResolveSource;
  editing: boolean;
  onEditing: (on: boolean) => void;
}

export function SyncConflictPane({ file, source, editing, onEditing }: Props) {
  const { t, i18n } = useTranslation();
  const area = areaLabel(t, file.area);
  const merged = file.agent_state === "merged_by_agent" && file.answer === null;
  const card = editing ? "editing" : merged ? "merged" : null;
  const openEditor = () => source.openEditor(file.path, () => onEditing(true));
  const leave = () => source.discard(file.path, () => onEditing(false));

  return (
    <div
      className="flex min-w-0 flex-1 flex-col gap-4 px-7 py-5"
      data-testid={`conflict-pane-${file.path}`}
    >
      <div className="flex items-start gap-2.5">
        <div className="flex min-w-0 flex-col gap-[3px]">
          <span className="truncate font-mono text-sm font-medium text-text">{file.path}</span>
          <span className="text-xs text-text-muted">
            {editing
              ? t("sync.resolve.editingMeta", { area })
              : t("sync.resolve.changed", {
                  area,
                  mine: clock(file.ours_time, i18n.language),
                  machine: otherMachine(t, file),
                  theirs: clock(file.theirs_time, i18n.language),
                })}
          </span>
        </div>
        {file.secret ? null : (
          <div className="ml-auto flex shrink-0 items-center gap-2">
            {card ? null : (
              <Button
                type="button"
                variant="outline"
                size="sm"
                loading={source.editorBusy}
                onClick={openEditor}
              >
                <ExternalLink aria-hidden />
                {t("sync.resolve.openEditor")}
              </Button>
            )}
            {canAskAgent(file) ? (
              <AgentHandoff
                size="sm"
                prompt={({ agent }) => source.handoff({ paths: [file.path], agent })}
              />
            ) : null}
          </div>
        )}
      </div>
      {card ? (
        <SyncConflictCopyCard
          file={file}
          state={card}
          pending={source.busy}
          busy={source.editorBusy}
          error={source.error}
          onOpen={openEditor}
          onResolve={() => source.markResolved(file.path)}
          onBack={leave}
        />
      ) : (
        <>
          {file.agent_state === "handed_off" && file.answer === null ? (
            <p
              className="flex items-center gap-1.5 text-xs text-text-muted"
              data-testid="sync-conflict-handed"
            >
              <MessageSquare className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
              {t("sync.resolve.handedOff", {
                agent: file.agent_name ?? t("sync.resolve.copy.anAgent"),
                time: clock(file.agent_handed_at, i18n.language),
              })}
            </p>
          ) : null}
          <SyncConflictChoices
            file={file}
            join={source.mode === "join"}
            pending={source.busy}
            error={source.error}
            onChoose={(answer) => source.choose(file.path, answer)}
          />
        </>
      )}
    </div>
  );
}
