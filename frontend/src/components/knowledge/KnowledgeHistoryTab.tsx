// frontend/src/components/knowledge/KnowledgeHistoryTab.tsx
//
// A document's History (boards 5.1.03, 5.1.04, 5.1.29; spec web-ui "Show a
// knowledge document's history on its History tab"): its versions newest
// first in a list on the left — who wrote each (you, curation naming the agent
// whose item it curated, sync, an edit on disk), when, what it did and how
// many lines it moved — and the chosen one on the right: its diff against the
// version before, or against the document as it is now, with Restore this
// version, which writes a NEW version naming you rather than rewriting the
// past. A history that cannot be read says so here with a retry; the Document
// tab reads on its own and keeps working.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { History } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { KnowledgeVersionPanel } from "@/components/knowledge/KnowledgeVersionPanel";
import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { versionSentence, whenLabel, writerLabel } from "@/lib/knowledge/changes";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";
import { cn } from "@/lib/utils";

interface Props {
  path: string;
  /** The document's body as it is now — what Compare with current diffs against. */
  currentBody: string;
}

export function KnowledgeHistoryTab({ path, currentBody }: Props) {
  const { t, i18n } = useTranslation();
  const history = useDocumentHistory(path);
  const [chosen, setChosen] = useState<string | null>(null);

  if (history.isPending) {
    return (
      <div className="space-y-2 px-6 py-5" aria-busy>
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-3/5" />
      </div>
    );
  }
  if (history.error) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-6" role="alert">
        <EmptyState
          tone="error"
          title={t("knowledge.history.failedTitle")}
          description={`${translateApiError(t, history.error)} ${t("knowledge.history.failedFine")}`}
          action={
            <Button variant="outline" onClick={() => void history.refetch()}>
              {t("common.retry")}
            </Button>
          }
          secondaryAction={
            <Button variant="outline" asChild>
              <Link to="/activity">{t("knowledge.history.openActivity")}</Link>
            </Button>
          }
        />
      </div>
    );
  }

  const versions = history.data.versions;
  if (versions.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-6">
        <EmptyState icon={History} title={t("knowledge.history.none")} />
      </div>
    );
  }
  const selected = versions.find((v) => v.change.version === chosen) ?? versions[0];

  return (
    <div className="flex min-h-0 flex-1">
      <div
        role="group"
        aria-label={t("knowledge.history.versions")}
        className="flex w-[300px] shrink-0 flex-col gap-0.5 overflow-auto border-r border-border px-2 py-2.5"
      >
        <p className="flex items-center gap-2 px-2 pb-2 pt-1 text-2xs">
          <span className="font-semibold text-text-muted">
            {t("knowledge.history.countLabel", { count: versions.length })}
          </span>
          <span className="ml-auto text-text-subtle">{t("knowledge.history.newestFirst")}</span>
        </p>
        {versions.map((v, i) => {
          const c = v.change;
          const active = c.version === selected.change.version;
          const doc = c.documents.find((d) => d.path === path);
          return (
            <button
              key={c.version}
              type="button"
              onClick={() => setChosen(c.version)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "flex w-full gap-2.5 rounded-item px-2.5 py-[9px] text-left",
                active ? "bg-surface-selected" : "hover:bg-surface-hover",
              )}
            >
              <span className="pt-px">
                <KnowledgeWriterMark writer={c.writer} agent={c.agent} />
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="flex items-center gap-1.5">
                  <span className="text-sm font-label">{writerLabel(t, c)}</span>
                  <span className="text-xs text-text-muted">
                    {whenLabel(t, c.time, i18n.language)}
                  </span>
                  {i === 0 ? (
                    <span className="ml-auto inline-flex h-5 items-center rounded-sm bg-chip px-[7px] text-2xs font-label text-text-muted">
                      {t("knowledge.history.current")}
                    </span>
                  ) : null}
                </span>
                <span className="flex items-center gap-2">
                  <span className="truncate text-xs text-text-muted">{versionSentence(t, c)}</span>
                  {doc && (doc.added || doc.removed) ? (
                    <span className="ml-auto whitespace-nowrap font-mono text-2xs text-text-subtle">
                      {doc.added ? `+${doc.added}` : ""}
                      {doc.added && doc.removed ? " " : ""}
                      {doc.removed ? `−${doc.removed}` : ""}
                    </span>
                  ) : null}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      <KnowledgeVersionPanel
        key={selected.change.version}
        path={path}
        version={selected}
        isCurrent={selected === versions[0]}
        currentBody={currentBody}
      />
    </div>
  );
}
