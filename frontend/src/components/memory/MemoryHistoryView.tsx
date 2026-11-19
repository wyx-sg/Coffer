// frontend/src/components/memory/MemoryHistoryView.tsx
//
// Every change to memory (spec memory "Tidy memory as one change"; spec web-ui
// "Show a vault file's history on a History tab"): the versions of the hub's
// folder in the vault, newest first, each naming its writer — an agent's own
// edit, a person's edit on this page, a tidy as one change — with its diff and
// Restore this version…, in the version card every history shares
// (VaultHistoryView). Restoring the version before a tidy undoes the tidy.
// Opened from the ⋯ menu and named in the address (`history=1`); its ✕ or Esc
// goes back to the projects.
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { VaultHistoryView } from "@/components/history/VaultHistoryView";
import { Button } from "@/components/ui/button";

interface Props {
  onClose: () => void;
}

export function MemoryHistoryView({ onClose }: Props) {
  const { t } = useTranslation();
  return (
    <section
      aria-label={t("memory.history.label")}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
      className="flex min-h-0 min-w-0 flex-1 flex-col border-t border-border-subtle"
    >
      <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-border-subtle pl-6 pr-3">
        <h2 className="text-md font-semibold text-text">{t("memory.history.title")}</h2>
        <span className="min-w-0 truncate font-mono text-xs text-text-muted">memory/</span>
        <Button
          variant="ghost"
          size="icon-sm"
          className="ml-auto shrink-0"
          aria-label={t("memory.history.close")}
          onClick={onClose}
        >
          <X aria-hidden />
        </Button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col px-6 py-4">
        <VaultHistoryView path="memory/" storageKey="memory-history" fill="parent" />
      </div>
    </section>
  );
}
