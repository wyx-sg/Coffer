// frontend/src/kinds/memory/MemoryFactViewer.tsx
//
// Right-hand preview for the selected memory fact (mirrors the KB document
// viewer). Memory is AI-authored (agents write via the MCP `remember` tool);
// the UI renders facts READ-ONLY. Humans correct a fact by editing its file in
// their own editor — the <FileActions> bar opens / reveals / copies the
// absolute path — or delete it outright.
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileActions } from "@/components/FileActions";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { FactOut } from "./api";

interface Props {
  fact: FactOut | undefined;
  isDeletePending: boolean;
  onDelete: () => void;
  /** Recall query to pre-highlight in the body ("" = no highlight). */
  initialQuery?: string;
}

export function MemoryFactViewer({ fact, isDeletePending, onDelete, initialQuery }: Props) {
  const { t } = useTranslation();

  if (!fact) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center rounded-md border border-dashed border-border">
        <p className="text-sm text-muted-foreground">{t("memory.detail.selectFact")}</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium">{fact.name || t("memory.detail.untitled")}</span>
          <Badge variant="outline">{fact.actor}</Badge>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {fact.path ? <FileActions filePath={fact.path} /> : null}
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

      {fact.description ? (
        <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
          {fact.description}
        </p>
      ) : null}

      <FindableMarkdown className="max-h-[60vh] overflow-auto p-4" initialQuery={initialQuery}>
        {fact.text}
      </FindableMarkdown>
    </div>
  );
}
