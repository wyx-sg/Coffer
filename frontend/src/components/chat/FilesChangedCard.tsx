// src/components/chat/FilesChangedCard.tsx — "Files changed" inside an agent's
// reply, after its text and before the token line: the files the reply wrote,
// with the lines added and removed. A finished reply reads the files the daemon
// recorded for it; an older one falls back to the estimate its tool calls give
// (lib/conversations/filesChanged). A recorded row with a diff is a button that
// reports its path to `onOpenFile` (the diff drawer opens from it); the rest are
// plain rows. `selectedPath` marks the row whose diff is open. Nothing renders
// for a reply that changed no file.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { LineCounts } from "@/components/change-preview/LineCounts";
import { TruncatedText } from "@/components/ui/truncated-text";
import { relativeToCwd, type FileChange } from "@/lib/conversations/filesChanged";
import { useAgentConfig, useReplyFiles } from "@/lib/hooks/useConversations";
import { cn } from "@/lib/utils";

interface Props {
  conversationId: string;
  /** The persisted reply; null for a reply that has no row yet (its files are the estimate). */
  messageId: string | null;
  /** The tool-call estimate, used when no files were recorded for the reply. */
  estimate: FileChange[];
  onOpenFile?: (path: string) => void;
  selectedPath?: string | null;
}

export function FilesChangedCard({
  conversationId,
  messageId,
  estimate,
  onOpenFile,
  selectedPath,
}: Props) {
  const { t } = useTranslation();
  const recorded = useReplyFiles(conversationId, messageId);
  const { data: agentConfig } = useAgentConfig(conversationId, !!messageId);
  const cwd = agentConfig?.cwd ?? null;
  const rows: (FileChange & { hasDiff: boolean })[] =
    recorded.data && recorded.data.length > 0
      ? recorded.data.map((f) => ({
          path: f.path,
          added: f.added,
          removed: f.removed,
          hasDiff: f.has_diff,
        }))
      : estimate.map((f) => ({ ...f, hasDiff: false }));
  if (rows.length === 0) return null;
  return (
    <section
      aria-label={t("conversations.files.title")}
      className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised text-xs"
    >
      <h3 className="border-b border-border-subtle px-3 py-2 text-xs font-semibold text-text">
        {t("conversations.files.title")}
      </h3>
      <ul>
        {rows.map((f) => {
          const shown = relativeToCwd(f.path, cwd);
          const content = (
            <>
              <FileText className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
              <TruncatedText text={f.path} mono className="flex-1 text-text">
                {shown}
              </TruncatedText>
              <LineCounts added={f.added} removed={f.removed} />
            </>
          );
          const base = "flex h-8 w-full items-center gap-2 px-3 text-left";
          return (
            <li key={f.path} className="border-b border-border-subtle last:border-b-0">
              {f.hasDiff ? (
                <button
                  type="button"
                  onClick={() => onOpenFile?.(f.path)}
                  aria-current={selectedPath === f.path ? "true" : undefined}
                  className={cn(
                    base,
                    "transition-colors duration-fast hover:bg-surface-hover",
                    selectedPath === f.path && "bg-accent-soft",
                  )}
                >
                  {content}
                </button>
              ) : (
                <div className={base}>{content}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
