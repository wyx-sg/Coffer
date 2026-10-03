// src/components/chat/FilesChangedCard.tsx — "Files changed" inside an agent's
// reply, after its text and before the token line: each file its tool calls
// wrote, with the lines added and removed (lib/conversations/filesChanged). A
// row is a button that reports its path to `onOpenFile` (the diff drawer opens
// from it); `selectedPath` marks the row whose diff is open. Nothing renders
// for a reply that changed no file.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { LineCounts } from "@/components/change-preview/LineCounts";
import type { FileChange } from "@/lib/conversations/filesChanged";
import { cn } from "@/lib/utils";

interface Props {
  files: FileChange[];
  onOpenFile?: (path: string) => void;
  selectedPath?: string | null;
}

export function FilesChangedCard({ files, onOpenFile, selectedPath }: Props) {
  const { t } = useTranslation();
  if (files.length === 0) return null;
  return (
    <section
      aria-label={t("conversations.files.title")}
      className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised text-xs"
    >
      <h3 className="border-b border-border-subtle px-3 py-2 text-xs font-semibold text-text">
        {t("conversations.files.title")}
      </h3>
      <ul>
        {files.map((f) => (
          <li key={f.path} className="border-b border-border-subtle last:border-b-0">
            <button
              type="button"
              onClick={() => onOpenFile?.(f.path)}
              aria-current={selectedPath === f.path ? "true" : undefined}
              className={cn(
                "flex h-8 w-full items-center gap-2 px-3 text-left transition-colors duration-fast hover:bg-surface-hover",
                selectedPath === f.path && "bg-accent-soft",
              )}
            >
              <FileText className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-mono text-text">{f.path}</span>
              <LineCounts added={f.added} removed={f.removed} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
