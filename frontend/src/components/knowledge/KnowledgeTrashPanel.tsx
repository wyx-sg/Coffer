// frontend/src/components/knowledge/KnowledgeTrashPanel.tsx
// The trash surface for a scope (FR-023): soft-deleted DOCUMENTS with Restore
// and Purge. Restore re-converts from the kept original and re-indexes; Purge
// (a second delete) removes the original + the row for good. Notes never
// tombstone, so the trash is documents-only. Rendered as a dialog opened from
// the page header.
import { useTranslation } from "react-i18next";
import { RotateCcw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { KnowledgeItem } from "@/lib/api/knowledge";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: KnowledgeItem[];
  isLoading: boolean;
  isBusy: boolean;
  onRestore: (item: KnowledgeItem) => void;
  onPurge: (item: KnowledgeItem) => void;
}

export function KnowledgeTrashPanel({
  open,
  onOpenChange,
  items,
  isLoading,
  isBusy,
  onRestore,
  onPurge,
}: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("knowledge.trash.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.trash.hint")}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[55vh] space-y-2 overflow-auto">
          {isLoading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{t("common.loading")}</p>
          ) : items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {t("knowledge.trash.empty")}
            </p>
          ) : (
            items.map((item) => (
              <div
                key={item.ref}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
              >
                <div className="min-w-0">
                  <span className="block truncate font-medium">
                    {item.title || t("knowledge.untitled")}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {item.kbName}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={isBusy}
                    onClick={() => onRestore(item)}
                  >
                    <RotateCcw className="mr-1.5 size-3.5" /> {t("knowledge.trash.restore")}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                    disabled={isBusy}
                    onClick={() => onPurge(item)}
                    title={t("knowledge.trash.purgeHint")}
                  >
                    <Trash2 className="mr-1.5 size-3.5" /> {t("knowledge.trash.purge")}
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
