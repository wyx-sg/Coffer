// frontend/src/components/knowledge/KnowledgeCompareDialog.tsx
//
// Compare, after a stale save: what the document says on disk now against the
// text the person typed — additions are theirs, deletions are what the disk
// has that their draft does not. Read-only; the way out is still Reload or
// Copy my text in the editor.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeDiff } from "@/components/knowledge/KnowledgeDiff";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { diffLines } from "@/lib/knowledge/lineDiff";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDisk: string;
  mine: string;
}

export function KnowledgeCompareDialog({ open, onOpenChange, onDisk, mine }: Props) {
  const { t } = useTranslation();
  const rows = useMemo(() => (open ? diffLines(onDisk, mine) : []), [open, onDisk, mine]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("knowledge.editor.compareTitle")}</DialogTitle>
          <DialogDescription>{t("knowledge.editor.compareBody")}</DialogDescription>
        </DialogHeader>
        <KnowledgeDiff rows={rows} className="max-h-[60vh]" />
      </DialogContent>
    </Dialog>
  );
}
