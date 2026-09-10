// frontend/src/lib/fileActionItems.ts
// The open-in-editor / reveal actions as descriptors, shared by the inline
// `FileActions` bar (components/FileActions.tsx) and the RowActions "⋯" overflow
// menu (components/RowActions.tsx). Lives apart from the FileActions component so
// that file stays component-only (React fast refresh).
//
// The actual open/reveal goes through useFsActions, which calls the loopback
// daemon (spec agent-registry FR-039, ADR daemon-proxies-os-file-actions). Coffer's viewers are read-only — editing happens in the user's own
// editor, not in-app.
import { useTranslation } from "react-i18next";
import { ExternalLink, FolderOpen, type LucideIcon } from "lucide-react";

import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";
import { usePreferredEditor } from "@/lib/preferences";

export interface FileActionItem {
  key: string;
  label: string;
  icon: LucideIcon;
  onClick: () => void;
}

export function useFileActionItems(filePath: string): FileActionItem[] {
  const { t } = useTranslation();
  const { toast } = useToast();
  const editor = usePreferredEditor();
  const { open, reveal } = useFsActions();

  const doOpen = (path: string, failKey: string) =>
    void open(path, editor).catch(() => toast.error(t(failKey)));
  const doReveal = (path: string) =>
    void reveal(path).catch(() => toast.error(t("fileActions.revealFailed")));

  return [
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
}
