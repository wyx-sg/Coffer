// src/components/agents/UnsavedChangesDialog.tsx — leaving a config file with unsaved edits asks first (board 2.1.59).
//
// Names the file being edited and what the user is about to open instead, and
// says the file on disk is untouched: only the edits on screen go. Keep editing
// is the safe default; Discard changes applies the parked selection.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface Props {
  open: boolean;
  /** The file with the unsaved edits ("settings.json"). */
  file: string;
  /** What would open instead ("CLAUDE.md"); null when leaving the tab. */
  target: string | null;
  onKeepEditing: () => void;
  onDiscard: () => void;
}

export function UnsavedChangesDialog({ open, file, target, onKeepEditing, onDiscard }: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onKeepEditing()}>
      <DialogContent className="max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{t("agents.configTab.unsaved.title", { file })}</DialogTitle>
          <DialogDescription>
            {target
              ? t("agents.configTab.unsaved.body", { target })
              : t("agents.configTab.unsaved.leaveBody")}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={onKeepEditing}>
            {t("agents.configTab.unsaved.keep")}
          </Button>
          <Button variant="destructive" onClick={onDiscard}>
            {t("agents.configTab.unsaved.discard")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
