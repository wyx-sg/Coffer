// frontend/src/components/FileActions.tsx
// Coffer's file viewers are read-only (specs 002/004/005/006/007): editing
// happens in the user's own editor, not in-app. This shared action bar takes a
// managed file (or its containing folder) to those external tools — open it in
// the preferred editor (see the "preferred editor" preference in General
// settings) and reveal it in the OS file manager. The actual open/reveal goes
// through useFsActions: tauri-plugin-opener on the packaged desktop app, the
// loopback daemon on the web (spec 004 FR-039, ADR-033). The web and desktop
// surfaces now show the same buttons — there is no copy-path fallback.
import { useTranslation } from "react-i18next";
import { ExternalLink, Folder, FolderOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";
import { usePreferredEditor } from "@/lib/preferences";
import { cn } from "@/lib/utils";

export function FileActions({
  filePath,
  folderPath,
  className,
}: {
  /** Absolute on-disk path of the file being viewed. */
  filePath: string;
  /** Absolute on-disk path of its containing folder (enables folder actions). */
  folderPath?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const editor = usePreferredEditor();
  const { open, reveal } = useFsActions();

  const doOpen = (path: string, failKey: string) =>
    void open(path, editor).catch(() => toast.error(t(failKey)));
  const doReveal = (path: string) =>
    void reveal(path).catch(() => toast.error(t("fileActions.revealFailed")));

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => doOpen(filePath, "fileActions.openFailed")}
      >
        <ExternalLink className="mr-1.5 size-3.5" />
        {t("fileActions.openInEditor")}
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={() => doReveal(filePath)}>
        <FolderOpen className="mr-1.5 size-3.5" />
        {t("fileActions.reveal")}
      </Button>
      {folderPath ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => doOpen(folderPath, "fileActions.openFolderFailed")}
        >
          <Folder className="mr-1.5 size-3.5" />
          {t("fileActions.openFolder")}
        </Button>
      ) : null}
    </div>
  );
}
