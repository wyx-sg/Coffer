// frontend/src/lib/fileActionItems.ts
// The open-in-editor / reveal (+ optional open-folder) actions as descriptors,
// shared by the inline `FileActions` bar (components/FileActions.tsx) and the
// RowActions "⋯" overflow menu (components/RowActions.tsx). Lives apart from the
// FileActions component so that file stays component-only (React fast refresh).
//
// The actual open/reveal goes through useFsActions: tauri-plugin-opener on the
// packaged desktop app, the loopback daemon on the web (spec 004 FR-039,
// ADR-033). Coffer's viewers are read-only — editing happens in the user's own
// editor, not in-app.
import { useTranslation } from "react-i18next";
import { ExternalLink, Folder, FolderOpen, type LucideIcon } from "lucide-react";

import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";
import { usePreferredEditor } from "@/lib/preferences";

export interface FileActionItem {
  key: string;
  label: string;
  icon: LucideIcon;
  onClick: () => void;
}

export function useFileActionItems(filePath: string, folderPath?: string): FileActionItem[] {
  const { t } = useTranslation();
  const { toast } = useToast();
  const editor = usePreferredEditor();
  const { open, reveal } = useFsActions();

  const doOpen = (path: string, failKey: string) =>
    void open(path, editor).catch(() => toast.error(t(failKey)));
  const doReveal = (path: string) =>
    void reveal(path).catch(() => toast.error(t("fileActions.revealFailed")));

  const items: FileActionItem[] = [
    {
      key: "open",
      label: t("fileActions.openInEditor"),
      icon: ExternalLink,
      onClick: () => doOpen(filePath, "fileActions.openFailed"),
    },
    {
      key: "reveal",
      label: t("fileActions.reveal"),
      icon: FolderOpen,
      onClick: () => doReveal(filePath),
    },
  ];
  if (folderPath) {
    items.push({
      key: "openFolder",
      label: t("fileActions.openFolder"),
      icon: Folder,
      onClick: () => doOpen(folderPath, "fileActions.openFolderFailed"),
    });
  }
  return items;
}
