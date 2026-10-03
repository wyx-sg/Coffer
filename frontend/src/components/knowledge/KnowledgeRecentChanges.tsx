// frontend/src/components/knowledge/KnowledgeRecentChanges.tsx
//
// Recent changes (boards 5.1.21–5.1.24; spec web-ui "Follow knowledge changes
// in Recent changes"): one timeline across every collection, newest first, of
// curation passes and of documents people and agents wrote, restored or
// deleted — the last seven days, grouped by day. Filtered by Collection and
// Author pills whose choice lives in the address (`?collection=` `?author=`),
// with Clear filters once either is set. Above the timeline, the items still
// waiting to be curated with a quiet Curate now. A pass opens what it did and
// can be undone from there; a delete — of a document or of a whole collection —
// carries Restore (spec knowledge "Restore a deleted collection or document
// from Recent changes"). Without git the region says so and hands installing it
// to an agent; any other failed read is the one Load error row.
import { useSearchParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { History } from "lucide-react";

import { FilterPill } from "@/components/filters";
import { EmptyState } from "@/components/EmptyState";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { KnowledgeChangeRow } from "@/components/knowledge/KnowledgeChangeRow";
import { KnowledgeWaitingList } from "@/components/knowledge/KnowledgeWaitingList";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorHandoff } from "@/lib/api/errorHandoff";
import type { CollectionOut } from "@/lib/api/knowledge";
import {
  ANY_AUTHOR,
  authorOptions,
  groupByDay,
  matchesAuthor,
  restoredVersions,
  undoneVersions,
  withinDays,
} from "@/lib/knowledge/changes";
import { useKnowledgeChanges } from "@/lib/hooks/useKnowledgeHistory";

const ANY_COLLECTION = "any";

interface Props {
  collections: CollectionOut[];
  modelSet: boolean | undefined;
}

export function KnowledgeRecentChanges({ collections, modelSet }: Props) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const collection = params.get("collection");
  const author = params.get("author") ?? ANY_AUTHOR;
  const changes = useKnowledgeChanges(collection);

  const setFilter = (key: "collection" | "author", value: string, any: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value === any) next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );

  const all = changes.data?.changes ?? [];
  const undone = undoneVersions(all);
  const restored = restoredVersions(all);
  const shown = all.filter((c) => withinDays(c.time, 7) && matchesAuthor(c, author));
  // The authors the data names; a chosen author with no change here stays listed.
  const authors = authorOptions(t, all);
  if (author !== ANY_AUTHOR && !authors.some((a) => a.value === author)) {
    authors.push({ value: author, label: author.replace(/^agent:/, "") });
  }
  const filtered = collection !== null || author !== ANY_AUTHOR;
  // With git missing the refusal carries the prompt for installing it.
  const gitHandoff = errorHandoff(changes.error);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-3 px-8 pt-5">
        <h2 className="text-md font-semibold">{t("knowledge.recent.title")}</h2>
        <span className="text-xs text-text-muted">{t("knowledge.recent.window")}</span>
        {changes.error ? null : (
          <span className="ml-auto flex flex-wrap items-center gap-2">
            <FilterPill
              mode="single"
              label={t("knowledge.recent.collectionFilter")}
              value={collection}
              options={collections.map((c) => ({ value: c.name, label: c.name }))}
              onChange={(v) => setFilter("collection", v ?? ANY_COLLECTION, ANY_COLLECTION)}
            />
            <FilterPill
              mode="single"
              label={t("knowledge.recent.authorFilter")}
              value={author === ANY_AUTHOR ? null : author}
              options={authors}
              fixedOrder
              onChange={(v) => setFilter("author", v ?? ANY_AUTHOR, ANY_AUTHOR)}
            />
            {filtered ? (
              <button
                type="button"
                onClick={() => setParams({}, { replace: true })}
                className="ml-1 text-xs font-medium text-accent-text hover:underline"
              >
                {t("knowledge.recent.clearFilters")}
              </button>
            ) : null}
          </span>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-8 pb-7 pt-3.5">
        <div className="flex max-w-[760px] flex-col gap-[18px]">
          {modelSet !== false && changes.data ? (
            <KnowledgeWaitingList waiting={changes.data.waiting} collections={collections} />
          ) : null}

          {changes.isPending ? (
            <div className="space-y-2" aria-busy>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : changes.error ? (
            gitHandoff ? (
              <LoadErrorRow
                tone="neutral"
                title={t("knowledge.recent.needsGitTitle")}
                reason={t("knowledge.recent.needsGitBody")}
                actions={
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void changes.refetch()}
                    >
                      {t("knowledge.recent.checkAgain")}
                    </Button>
                    <AgentHandoff size="sm" help={false} prompt={gitHandoff} />
                  </>
                }
              />
            ) : (
              <LoadErrorRow
                title={t("knowledge.recent.failed")}
                error={changes.error}
                onRetry={() => void changes.refetch()}
                actions={
                  <Link to="/activity" className="text-xs font-label text-accent-text">
                    {t("knowledge.recent.openActivity")}
                  </Link>
                }
              />
            )
          ) : shown.length === 0 ? (
            <EmptyState icon={History} title={t("knowledge.recent.empty")} />
          ) : (
            groupByDay(shown).map(([day, group]) => (
              <section key={day} className="flex flex-col gap-2">
                <h3 className="flex min-h-control-sm items-center text-sm font-semibold text-text">
                  {day === "today" || day === "yesterday" ? t(`knowledge.recent.${day}`) : day}
                </h3>
                <ul className="flex flex-col">
                  {group.map((c) => (
                    <KnowledgeChangeRow
                      key={c.version}
                      change={c}
                      collections={collections}
                      undone={undone.has(c.version)}
                      restored={restored.has(c.version)}
                    />
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
