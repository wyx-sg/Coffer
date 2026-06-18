// frontend/src/components/FileActions.tsx
// Coffer's file viewers are read-only (specs 002/004/005/006/007): editing
// happens in the user's own editor, not in-app. This shared action bar takes a
// managed file to those external tools. In the packaged desktop app it opens
// the file (or its containing folder) in the preferred external editor — see
// the "preferred editor" preference in General settings — and reveals it in the
// OS file manager via tauri-plugin-opener. On the web, where a browser cannot
// touch the filesystem, it falls back to copying the absolute path to the
// clipboard. Mirrors FolderPicker's isTauri() + static-specifier dynamic-import
// pattern so Vite bundles the plugin for the packaged WebView.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, ExternalLink, Folder, FolderOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { usePreferredEditor } from "@/lib/preferences";
import { isTauri } from "@/lib/tauri";
import { cn } from "@/lib/utils";

/** Open a path in the user's preferred editor (empty preference = OS default). */
async function openInEditor(path: string, editor: string): Promise<void> {
  const { openPath } = await import("@tauri-apps/plugin-opener");
  await openPath(path, editor || undefined);
}

async function revealInFileManager(path: string): Promise<void> {
  const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
  await revealItemInDir(path);
}

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
  const [copied, setCopied] = useState<"file" | "folder" | null>(null);
  const tauri = isTauri();

  const copy = (path: string, which: "file" | "folder") => {
    void navigator.clipboard.writeText(path).then(
      () => {
        setCopied(which);
        setTimeout(() => setCopied(null), 2000);
      },
      () => toast.error(t("fileActions.copyFailed")),
    );
  };

  const open = (path: string, failKey: string) =>
    void openInEditor(path, editor).catch(() => toast.error(t(failKey)));
  const reveal = (path: string) =>
    void revealInFileManager(path).catch(() => toast.error(t("fileActions.revealFailed")));

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {tauri ? (
        <>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => open(filePath, "fileActions.openFailed")}
          >
            <ExternalLink className="mr-1.5 size-3.5" />
            {t("fileActions.openInEditor")}
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => reveal(filePath)}>
            <FolderOpen className="mr-1.5 size-3.5" />
            {t("fileActions.reveal")}
          </Button>
          {folderPath ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => open(folderPath, "fileActions.openFolderFailed")}
            >
              <Folder className="mr-1.5 size-3.5" />
              {t("fileActions.openFolder")}
            </Button>
          ) : null}
        </>
      ) : (
        <>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => copy(filePath, "file")}
            aria-label={t("fileActions.copyPath")}
          >
            <Copy className="mr-1.5 size-3.5" />
            {copied === "file" ? t("fileActions.copied") : t("fileActions.copyPath")}
          </Button>
          {folderPath ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => copy(folderPath, "folder")}
              aria-label={t("fileActions.copyFolderPath")}
            >
              <Copy className="mr-1.5 size-3.5" />
              {copied === "folder" ? t("fileActions.copied") : t("fileActions.copyFolderPath")}
            </Button>
          ) : null}
        </>
      )}
    </div>
  );
}
