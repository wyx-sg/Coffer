// frontend/src/lib/knowledge/obsidian.ts
//
// **Open in Obsidian** (spec knowledge "Open a collection in Obsidian when it
// is installed"): a ⋯ menu item on a collection and on a file, shown only when
// the daemon detects Obsidian on this machine — a person who does not use it
// never sees the word. It opens the path with the app, as Open in editor does
// with the preferred editor; a collection's folder is one Obsidian vault.
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";
import { useDetectedEditors } from "@/lib/hooks/useEditors";

/** A ⋯ menu item, in the shape the menu takes. */
export interface ObsidianItem {
  key: string;
  label: string;
  onSelect: () => void;
}

/** The ⋯ menu item that opens `path` in Obsidian, or null when Obsidian is
 *  not installed (or detection has not answered yet). */
export function useOpenInObsidian(path: string): ObsidianItem | null {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { open } = useFsActions();
  const editors = useDetectedEditors();
  const obsidian = editors.data?.find((e) => e.label === "Obsidian");
  if (!obsidian || !path) return null;
  return {
    key: "obsidian",
    label: t("knowledge.obsidian.open"),
    onSelect: () =>
      void open(path, obsidian.value).catch(() => toast.error(t("fileActions.openFailed"))),
  };
}
