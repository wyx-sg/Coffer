// frontend/src/pages/sync/SyncConflictFileList.tsx
//
// The left pane of Resolve conflicts (the shared review nav): every file the round stopped on, each
// with what its answer is so far. An answered file carries a check, an
// unanswered one a red dot, one open in the editor a pencil, an encrypted
// secret a lock, and one an agent merged a speech bubble: check it.
import { Check, Lock, MessageSquare, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { ConflictFile } from "@/lib/api/sync";
import { fileState } from "./syncConflictFormat";
import { SyncReviewNav } from "./SyncReviewShell";

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
    <SyncReviewNav
      selected={selected}
      onSelect={onSelect}
      items={files.map((file) => {
        const isEditing = editing.has(file.path) && file.answer === null;
        return {
          path: file.path,
          mark: <Mark file={file} editing={isEditing} />,
          note: fileState(t, file, isEditing),
          testId: `conflict-file-${file.path}`,
        };
      })}
    />
  );
}
