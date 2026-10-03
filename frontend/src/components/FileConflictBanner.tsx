// frontend/src/components/FileConflictBanner.tsx — a save refused as stale.
//
// The danger banner the knowledge document editor and the memory editor both
// put over the text when the daemon says the file changed since it was read
// (409 `KNOWLEDGE_FILE_CONFLICT` / `MEMORY_NOTE_CONFLICT`): what changed and
// that the text is not saved, with three ways out — Compare, Copy my text, and
// Reload… (take what is on disk, after asking, because it drops the draft).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

interface Props {
  title: string;
  /** The second line: who changed the file and when, then that the text is not saved. */
  text: string;
  onCompare: () => void;
  onCopyMine: () => void;
  /** Take the disk's version, dropping the draft (asked first, here). */
  onReload: () => void;
}

export function FileConflictBanner({ title, text, onCompare, onCopyMine, onReload }: Props) {
  const { t } = useTranslation();
  const [confirmReload, setConfirmReload] = useState(false);
  return (
    <>
      <div
        role="alert"
        className="flex shrink-0 items-center gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5"
      >
        <AlertTriangle className="size-[15px] shrink-0 text-danger" aria-hidden />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs text-text-muted">{text}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button variant="outline" size="sm" onClick={onCompare}>
            {t("knowledge.editor.compare")}
          </Button>
          <Button variant="outline" size="sm" onClick={onCopyMine}>
            {t("knowledge.editor.copyMine")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-danger"
            onClick={() => setConfirmReload(true)}
          >
            {t("knowledge.editor.reloadAsk")}
          </Button>
        </div>
      </div>
      <ConfirmDialog
        open={confirmReload}
        onOpenChange={setConfirmReload}
        title={t("knowledge.editor.reloadTitle")}
        description={t("knowledge.editor.reloadBody")}
        confirmLabel={t("knowledge.editor.reloadConfirm")}
        onConfirm={() => {
          setConfirmReload(false);
          onReload();
        }}
      />
    </>
  );
}
