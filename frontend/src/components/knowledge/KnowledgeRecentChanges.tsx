// frontend/src/components/knowledge/KnowledgeRecentChanges.tsx
//
// Recent changes (boards 5.1.07, 5.1.08, 5.1.27; spec web-ui "Follow
// knowledge changes in Recent changes"): one timeline across every
// collection, newest first, of curation passes and of documents people and
// agents wrote, restored or deleted — the last seven days, grouped by day,
// filterable to one collection and by who wrote it. Above it, the items still
// waiting to be curated with the quiet Curate now. A pass opens what it did
// and can be undone from there; a delete — of a document or of a whole
// collection — carries Restore, which puts it back from the vault's history
// (spec knowledge "Restore a deleted collection or document from Recent
// changes").
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { History } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import { Section, SectionStack } from "@/components/Section";
import { EmptyState } from "@/components/EmptyState";
import { FilterPill } from "@/components/filters";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { KnowledgeChangeRow } from "@/components/knowledge/KnowledgeChangeRow";
import { KnowledgeWaitingList } from "@/components/knowledge/KnowledgeWaitingList";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import {
  groupByDay,
  matchesWriter,
  restoredVersions,
  undoneVersions,
  withinDays,
  type WriterFilter,
} from "@/lib/knowledge/changes";
import { useKnowledgeChanges } from "@/lib/hooks/useKnowledgeHistory";

const WRITERS: WriterFilter[] = ["everyone", "agents", "you"];

interface Props {
  collections: CollectionOut[];
  modelSet: boolean | undefined;
}

export function KnowledgeRecentChanges({ collections, modelSet }: Props) {
  const { t } = useTranslation();
  const [collection, setCollection] = useState<string | null>(null);
  const [writer, setWriter] = useState<WriterFilter>("everyone");
  const changes = useKnowledgeChanges(collection);

  const all = changes.data?.changes ?? [];
  const undone = undoneVersions(all);
  const restored = restoredVersions(all);
  const shown = all.filter((c) => withinDays(c.time, 7) && matchesWriter(c, writer));
  // With git missing the refusal carries the prompt for installing it.
  const gitHandoff = errorHandoff(changes.error);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-3 px-8 pt-5">
        <h2 className="text-[16px] font-bold">{t("knowledge.recent.title")}</h2>
        <HelpTip>{t("knowledge.recent.window")}</HelpTip>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          <Segmented<WriterFilter>
            value={writer}
            onChange={setWriter}
            label={t("knowledge.recent.writerFilter")}
            options={WRITERS.map((w) => ({ value: w, label: t(`knowledge.recent.writer.${w}`) }))}
          />
          <FilterPill
            mode="single"
            label={t("knowledge.recent.collectionFilter")}
            options={collections.map((c) => ({ value: c.name, label: c.name }))}
            value={collection}
            onChange={setCollection}
          />
        </span>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-8 pb-7 pt-3.5">
        <SectionStack className="max-w-[760px]">
          {modelSet !== false && changes.data ? (
            <KnowledgeWaitingList waiting={changes.data.waiting} collections={collections} />
          ) : null}

          {changes.isPending ? (
            <div className="space-y-2" aria-busy>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : changes.error ? (
            <EmptyState
              tone="error"
              title={t("knowledge.recent.failed")}
              description={translateApiError(t, changes.error)}
              action={<Button onClick={() => void changes.refetch()}>{t("common.retry")}</Button>}
            >
              {gitHandoff ? (
                <div className="flex justify-center">
                  <AgentHandoff prompt={gitHandoff} size="sm" />
                </div>
              ) : null}
            </EmptyState>
          ) : shown.length === 0 ? (
            <EmptyState icon={History} title={t("knowledge.recent.empty")} />
          ) : (
            groupByDay(shown).map(([day, group]) => (
              <Section
                key={day}
                title={day === "today" || day === "yesterday" ? t(`knowledge.recent.${day}`) : day}
                gap="snug"
              >
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
              </Section>
            ))
          )}
        </SectionStack>
      </div>
    </div>
  );
}
