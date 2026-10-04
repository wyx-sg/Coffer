// frontend/src/pages/sync/SyncConflictFileList.tsx
//
// The left pane of Resolve conflicts: every file the round stopped on, each
// with what its answer is so far. An answered file carries a check, an
// unanswered one a red dot, one open in the editor a pencil, an encrypted
// secret a lock, and one an agent merged a speech bubble: check it.
import { Check, Lock, MessageSquare, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { ConflictFile } from "@/lib/api/sync";
import { cn } from "@/lib/utils";
import { fileState } from "./syncConflictFormat";

interface Props {
  files: ConflictFile[];
  selected: string;
  editing: ReadonlySet<string>;
  onSelect: (path: string) => void;
}

function Mark({ file, editing }: { file: ConflictFile; editing: boolean }) {
  if (file.answer) return <Check className="size-3.5 text-success" aria-hidden />;
  if (editing) return <Pencil className="size-3.5 text-text-subtle" aria-hidden />;
  if (file.agent_state === "merged_by_agent") {
    return <MessageSquare className="size-3.5 text-accent" aria-hidden />;
  }
  if (file.secret) return <Lock className="size-3.5 text-text-subtle" aria-hidden />;
  return <span aria-hidden className="mx-[3px] size-2 shrink-0 rounded-full bg-danger" />;
}

export function SyncConflictFileList({ files, selected, editing, onSelect }: Props) {
  const { t } = useTranslation();
  return (
    <nav
      aria-label={t("sync.resolve.filesLabel")}
      className="flex w-[300px] shrink-0 flex-col gap-0.5 border-r border-border bg-surface-sidebar px-2 py-3"
    >
      <p className="px-2.5 pb-1 text-2xs font-semibold uppercase tracking-[.02em] text-text-muted">
        {t("sync.resolve.files")}
      </p>
      {files.map((file) => {
        const current = file.path === selected;
        const isEditing = editing.has(file.path) && file.answer === null;
        return (
          <button
            key={file.path}
            type="button"
            aria-current={current || undefined}
            onClick={() => onSelect(file.path)}
            data-testid={`conflict-file-${file.path}`}
            className={cn(
              "flex items-start gap-2 rounded-item px-2.5 py-2 text-left transition-colors duration-fast",
              current ? "bg-surface-selected" : "hover:bg-surface-hover",
            )}
          >
            <span className="inline-flex pt-0.5">
              <Mark file={file} editing={isEditing} />
            </span>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate font-mono text-xs text-text">{file.path}</span>
              <span className="text-xs text-text-muted">{fileState(t, file, isEditing)}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}
