// frontend/src/components/memory/MemoryWelcomePanel.tsx — "Nothing distilled yet", the first-run state of /memory.
//
// Shown before any partition exists, in the shared EmptyState every other
// first-run surface uses. The one next step is Update memory, not Add:
// nothing here is user-created — Coffer distils what the agents already
// learned out of their own memory and never writes back to it.
import { Brain } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";

export function MemoryWelcomePanel() {
  const { t } = useTranslation();
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-raised">
      <EmptyState
        icon={Brain}
        title={t("memory.welcome.title")}
        description={t("memory.welcome.body")}
        action={<MemoryUpdateButton />}
      />
    </div>
  );
}
