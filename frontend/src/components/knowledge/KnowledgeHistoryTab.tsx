// frontend/src/components/knowledge/KnowledgeHistoryTab.tsx
//
// A document's History (spec web-ui "Show a knowledge document's history on
// its History tab"): its versions newest first — who wrote each (you,
// curation naming the agent whose item it curated, sync, an edit on disk) and
// when — and, for the chosen one, its diff against the version before, with
// Restore this version, which writes a NEW version naming you rather than
// rewriting the past. A history that cannot be read says so here with a
// retry; the Document tab reads on its own and keeps working.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { KnowledgeVersionPanel } from "@/components/knowledge/KnowledgeVersionPanel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { changeSentence, writerLabel } from "@/lib/knowledge/changes";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";
import { cn, formatDateTime } from "@/lib/utils";

export function KnowledgeHistoryTab({ path }: { path: string }) {
  const { t } = useTranslation();
  const history = useDocumentHistory(path);
  const [chosen, setChosen] = useState<string | null>(null);

  if (history.isPending) {
    return (
      <div className="space-y-2" aria-busy>
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-3/5" />
      </div>
    );
  }
  if (history.error) {
    return (
      <div role="alert" className="space-y-2 rounded-md border border-border-subtle p-4">
        <p className="text-sm font-semibold">{t("knowledge.history.failedTitle")}</p>
        <p className="text-sm text-text-muted">{translateApiError(t, history.error)}</p>
        <p className="text-xs text-text-subtle">{t("knowledge.history.failedFine")}</p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => void history.refetch()}>
            {t("common.retry")}
          </Button>
          <Button size="sm" variant="ghost" asChild>
            <Link to="/activity">{t("knowledge.history.openActivity")}</Link>
          </Button>
        </div>
      </div>
    );
  }

  const versions = history.data.versions;
  if (versions.length === 0) {
    return <p className="text-sm text-text-subtle">{t("knowledge.history.none")}</p>;
  }
  const selected = versions.find((v) => v.change.version === chosen) ?? versions[0];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto">
      <div className="shrink-0 space-y-1">
        <p className="text-xs text-text-subtle">
          {t("knowledge.history.count", { count: versions.length })}
        </p>
        <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
          {versions.map((v, i) => {
            const c = v.change;
            const active = c.version === selected.change.version;
            return (
              <li key={c.version}>
                <button
                  type="button"
                  onClick={() => setChosen(c.version)}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "flex w-full flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2 text-left text-sm",
                    active ? "bg-surface-selected" : "hover:bg-surface-hover",
                  )}
                >
                  <span className="font-medium">{writerLabel(t, c)}</span>
                  <span className="text-xs text-text-subtle">{formatDateTime(c.time)}</span>
                  {i === 0 ? (
                    <span className="rounded-sm bg-chip px-1.5 text-2xs text-text-muted">
                      {t("knowledge.history.current")}
                    </span>
                  ) : null}
                  <span className="w-full truncate text-xs text-text-muted">
                    {changeSentence(t, c)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      <KnowledgeVersionPanel path={path} version={selected} isCurrent={selected === versions[0]} />
    </div>
  );
}
