// frontend/src/components/memory/MemoryToSort.tsx
//
// The Memory page's reminder to sort task notes (spec memory "Sort task
// material into knowledge on request"): how many memories the agents filed as
// task notes wait to be sorted, and **Sort into knowledge**, which opens Claude
// Code in the person's terminal with a prompt listing them. Claude Code
// proposes where each goes (knowledge, a skill, memory, nothing), acts once the
// person agrees and records each one, so the count falls as it works. Coffer
// never starts the sorting on its own. Nothing shows while nothing waits.
import { useTranslation } from "react-i18next";
import { Library } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSortIntoKnowledge } from "@/lib/hooks/useMemory";

export function MemoryToSort({ count }: { count: number }) {
  const { t } = useTranslation();
  const sort = useSortIntoKnowledge();
  if (count <= 0) return null;
  return (
    <div
      role="status"
      data-testid="memory-to-sort"
      className="flex items-center gap-3 rounded-xl border border-border-subtle bg-surface-raised px-3.5 py-2.5"
    >
      <Library className="size-[15px] shrink-0 text-text-muted" aria-hidden />
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-sm font-semibold text-text">{t("memory.toSort.line", { count })}</p>
        <p className="text-xs text-text-muted">{t("memory.toSort.hint")}</p>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="ml-auto shrink-0"
        loading={sort.isPending}
        onClick={() => sort.mutate()}
      >
        {t("memory.toSort.button")}
      </Button>
    </div>
  );
}
