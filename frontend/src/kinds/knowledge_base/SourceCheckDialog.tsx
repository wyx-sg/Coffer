// frontend/src/kinds/knowledge_base/SourceCheckDialog.tsx
//
// Reports the result of a "Check sources" scan (FR-021..024): one row per
// document with a tracked external source file, each tagged with its status
// (unchanged / changed / missing / edited / updated). Only a "changed" row
// offers a per-doc "Update from source" action (re-ingest in place); "edited"
// rows are blocked to avoid clobbering local edits, "missing" rows note the
// gone source file. Web-uploaded docs have no source file and never appear, so
// an empty report shows a calm explanation. Presentational — the page owns the
// scan/update mutations and toasts.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SourceCheckResponse, SourceStatus } from "./api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: SourceCheckResponse;
  /** The document id currently being re-ingested (shows per-row pending). */
  updatingId: string | null;
  onUpdate: (documentId: string) => void;
}

// Badge variant per status; "changed" / "updated" get a tinted className on top
// of the base variant so amber/green read at a glance.
const STATUS_VARIANT: Record<SourceStatus, "secondary" | "outline" | "destructive"> = {
  unchanged: "secondary",
  changed: "outline",
  missing: "destructive",
  edited: "secondary",
  updated: "secondary",
};

const STATUS_CLASS: Partial<Record<SourceStatus, string>> = {
  changed: "text-amber-600 dark:text-amber-500",
  updated: "text-emerald-600 dark:text-emerald-500",
};

export function SourceCheckDialog({ open, onOpenChange, report, updatingId, onUpdate }: Props) {
  const { t } = useTranslation();
  const { sources } = report;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledgeBases.detail.sourceCheck.title")}</DialogTitle>
          <DialogDescription>
            {t("knowledgeBases.detail.sourceCheck.description")}
          </DialogDescription>
        </DialogHeader>

        {sources.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("knowledgeBases.detail.sourceCheck.empty")}
          </p>
        ) : (
          <ul className="max-h-80 space-y-2 overflow-y-auto">
            {sources.map((s) => (
              <li
                key={s.document_id}
                className="flex items-start justify-between gap-3 rounded-md border p-3"
              >
                <div className="min-w-0 space-y-1">
                  <p className="truncate text-sm font-medium">{s.title}</p>
                  <p className="truncate text-xs text-muted-foreground" title={s.source_path}>
                    {s.source_path}
                  </p>
                  {s.status === "missing" ? (
                    <p className="text-xs text-destructive">
                      {t("knowledgeBases.detail.sourceCheck.missingNote")}
                    </p>
                  ) : null}
                  {s.status === "edited" ? (
                    <p className="text-xs text-muted-foreground">
                      {t("knowledgeBases.detail.sourceCheck.editedNote")}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <Badge
                    variant={STATUS_VARIANT[s.status]}
                    className={STATUS_CLASS[s.status]}
                  >
                    {t(`knowledgeBases.detail.sourceCheck.status.${s.status}`)}
                  </Badge>
                  {s.status === "changed" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={updatingId === s.document_id}
                      onClick={() => onUpdate(s.document_id)}
                    >
                      {t("knowledgeBases.detail.sourceCheck.update")}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
