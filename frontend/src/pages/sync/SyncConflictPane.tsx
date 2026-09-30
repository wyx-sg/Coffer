// frontend/src/pages/sync/SyncConflictPane.tsx
//
// The right pane of Resolve conflicts, for one file: its path and who changed
// it when, Open in editor, and then either the two choices (6.5.06) or the
// editor state (6.5.07). An encrypted secret (`secret/*.enc`) is only ever
// answered by one of the two choices — no editor, no agent merge, and its
// contents are never shown.
//
// Open in editor asks the daemon for the marked-up copy and has the OS open
// it (`useOpenInEditor`); the pane then waits for Mark resolved, which
// answers `edited` from the copy as saved.
import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { ConflictAnswer, ConflictFile } from "@/lib/api/sync";
import { useAnswerFile, useOpenInEditor } from "@/lib/hooks/useSyncStop";
import { SyncConflictChoices } from "./SyncConflictChoices";
import { SyncConflictEditing } from "./SyncConflictEditing";
import { areaLabel, clock, otherMachine } from "./syncConflictFormat";

interface Props {
  file: ConflictFile;
  /** The backend's "Merge with an agent" prompt for the round, if any. */
  handoff: string | null;
  editing: boolean;
  onEditing: (on: boolean) => void;
}

export function SyncConflictPane({ file, handoff, editing, onEditing }: Props) {
  const { t, i18n } = useTranslation();
  const answer = useAnswerFile();
  const editor = useOpenInEditor();
  const give = (value: ConflictAnswer) => answer.mutate({ path: file.path, answer: value });
  const area = areaLabel(t, file.area);

  return (
    <div
      className="flex min-w-0 flex-1 flex-col gap-4 px-7 py-5"
      data-testid={`conflict-pane-${file.path}`}
    >
      <div className="flex items-center gap-2.5">
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
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto"
            loading={editor.isPending}
            onClick={() => {
              answer.reset();
              editor.mutate(file.path, { onSuccess: () => onEditing(true) });
            }}
          >
            <ExternalLink aria-hidden />
            {t("sync.resolve.openEditor")}
          </Button>
        )}
      </div>
      {editing ? (
        <SyncConflictEditing
          file={file}
          pending={answer.isPending}
          error={answer.error}
          onResolve={() => give("edited")}
          onBack={() => {
            answer.reset();
            onEditing(false);
          }}
        />
      ) : (
        <SyncConflictChoices
          file={file}
          handoff={handoff}
          pending={answer.isPending}
          error={answer.error}
          onChoose={give}
        />
      )}
    </div>
  );
}
