// frontend/src/kinds/knowledge/KnowledgeEntryViewer.tsx
//
// Right-hand preview for the selected knowledge entry (mirrors the document
// viewer next door). Entries are agent-authored — written over the MCP gateway
// — so the UI renders them READ-ONLY. Humans correct an entry by editing its
// file in their own editor (the <FileActions> bar opens / reveals / copies the
// absolute path) or delete it outright.
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { FileActions } from "@/components/FileActions";
import { KnowledgePreviewBody } from "./KnowledgePreviewBody";
import type { EntryOut } from "./api";

interface Props {
  entry: EntryOut | undefined;
  isDeletePending: boolean;
  onDelete: () => void;
  /** Recall query to pre-highlight in the body ("" = no highlight). */
  initialQuery?: string;
}

export function KnowledgeEntryViewer({ entry, isDeletePending, onDelete, initialQuery }: Props) {
  const { t } = useTranslation();

  if (!entry) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center rounded-md border border-dashed border-border">
        <p className="text-sm text-muted-foreground">{t("knowledge.detail.selectEntry")}</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium">
            {entry.title || t("knowledge.detail.untitled")}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {entry.path ? <FileActions filePath={entry.path} /> : null}
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            onClick={onDelete}
            disabled={isDeletePending}
          >
            <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
          </Button>
        </div>
      </div>

      {entry.description ? (
        <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
          {entry.description}
        </p>
      ) : null}

      {/* `entry.text` is body-only (frontmatter stripped server-side); the shared
          preview is a no-op header in that case but keeps both lanes aligned and
          renders a clean header for any legacy file that still carries one. The
          entry's own description is shown above, so suppress the header's. */}
      <KnowledgePreviewBody
        text={entry.text}
        className="max-h-[60vh] overflow-auto p-4"
        initialQuery={initialQuery}
        hideDescription
      />
    </div>
  );
}
