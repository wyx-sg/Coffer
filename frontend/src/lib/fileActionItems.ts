// frontend/src/lib/fileActionItems.ts
// The open-in-editor / reveal actions as descriptors, rendered by the inline
// `FileActions` bar (components/FileActions.tsx). Lives apart from that
// component so it stays component-only (React fast refresh), and so a surface
// that wants these actions in some other shape can render the descriptors
// itself.
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
