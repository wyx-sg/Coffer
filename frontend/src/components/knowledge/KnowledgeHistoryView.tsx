// frontend/src/components/knowledge/KnowledgeHistoryView.tsx
//
// A knowledge file's history, over the whole Knowledge area (spec knowledge
// "Show a collection as one tree of read-only documents in the web UI"; spec
// web-ui "Show a vault file's history on a History tab"): the file's versions
// in the vault and their diffs, with Restore this version…, in the one version
// card every history shares (VaultHistoryView). While it is open the tree and
// the file make way for it, so the versions and the diff have the room; it is
// opened by the pane bar's History button and named in the address
// (`history=1`), and its ✕ or Esc goes back to the file.
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { VaultHistoryView } from "@/components/history/VaultHistoryView";
import { Button } from "@/components/ui/button";
import { vaultPathOf } from "@/lib/knowledge/routes";

interface Props {
  /** Knowledge-root-relative path of the open file. */
  path: string;
  onClose: () => void;
}

export function KnowledgeHistoryView({ path, onClose }: Props) {
  const { t } = useTranslation();
  const name = path.split("/").pop() ?? path;
  return (
    <section
      aria-label={t("knowledge.history.label", { name })}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-border-subtle pl-6 pr-3">
        <h2 className="text-md font-semibold text-text">{t("knowledge.history.title")}</h2>
        <span className="min-w-0 truncate font-mono text-xs text-text-muted" title={path}>
          {path}
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          className="ml-auto shrink-0"
          aria-label={t("knowledge.history.close")}
          onClick={onClose}
        >
          <X aria-hidden />
        </Button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col px-6 py-4">
        {/* The page is pinned to the window, so the history fills the area. */}
        <VaultHistoryView path={vaultPathOf(path)} storageKey="knowledge-history" fill="parent" />
      </div>
    </section>
  );
}
