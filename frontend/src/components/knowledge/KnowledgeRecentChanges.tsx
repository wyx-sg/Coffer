// frontend/src/components/knowledge/KnowledgeRecentChanges.tsx
//
// Recent changes (spec web-ui "Follow knowledge changes in Recent changes"):
// one timeline across every collection, newest first, of curation passes and
// of documents people and agents wrote or deleted — the last seven days,
// grouped by day, filterable to one collection and by who wrote it. Above it,
// the items still waiting to be curated with the quiet Curate now; choosing a
// change opens what it did, and a pass can be undone from there.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { History } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { KnowledgeChangeRow } from "@/components/knowledge/KnowledgeChangeRow";
import { KnowledgeNoModelLine } from "@/components/knowledge/KnowledgeNoModelLine";
import { KnowledgeWaitingList } from "@/components/knowledge/KnowledgeWaitingList";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import {
  groupByDay,
  matchesWriter,
  undoneVersions,
  withinDays,
  type WriterFilter,
} from "@/lib/knowledge/changes";
import { useKnowledgeChanges } from "@/lib/hooks/useKnowledgeHistory";
import { cn } from "@/lib/utils";

const ALL = "__all__";
const WRITERS: WriterFilter[] = ["everyone", "agents", "you"];

interface Props {
  collections: CollectionOut[];
  modelSet: boolean | undefined;
}

export function KnowledgeRecentChanges({ collections, modelSet }: Props) {
  const { t } = useTranslation();
  const [collection, setCollection] = useState<string>(ALL);
  const [writer, setWriter] = useState<WriterFilter>("everyone");
  const changes = useKnowledgeChanges(collection === ALL ? null : collection);

  const all = changes.data?.changes ?? [];
  const undone = undoneVersions(all);
  const shown = all.filter((c) => withinDays(c.time, 7) && matchesWriter(c, writer));

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto pb-6">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-bold">{t("knowledge.recent.title")}</h2>
        <span className="text-xs text-text-subtle">{t("knowledge.recent.window")}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div
            role="group"
            aria-label={t("knowledge.recent.writerFilter")}
            className="flex rounded-md border border-border p-0.5"
          >
            {WRITERS.map((w) => (
              <Button
                key={w}
                size="sm"
                variant="ghost"
                aria-pressed={writer === w}
                className={cn("h-6", writer === w && "bg-surface-selected text-text")}
                onClick={() => setWriter(w)}
              >
                {t(`knowledge.recent.writer.${w}`)}
              </Button>
            ))}
          </div>
          <Select value={collection} onValueChange={setCollection}>
            <SelectTrigger
              className="h-control-sm w-44"
              aria-label={t("knowledge.recent.collectionFilter")}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t("knowledge.recent.allCollections")}</SelectItem>
              {collections.map((c) => (
                <SelectItem key={c.uid} value={c.name}>
                  {c.title || c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      {modelSet === false ? (
        <KnowledgeNoModelLine />
      ) : changes.data ? (
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
        />
      ) : shown.length === 0 ? (
        <EmptyState icon={History} title={t("knowledge.recent.empty")} />
      ) : (
        groupByDay(shown).map(([day, group]) => (
          <section key={day} className="space-y-1">
            <h3 className="text-xs font-semibold text-text-subtle">
              {day === "today" || day === "yesterday" ? t(`knowledge.recent.${day}`) : day}
            </h3>
            <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
              {group.map((c) => (
                <KnowledgeChangeRow key={c.version} change={c} undone={undone.has(c.version)} />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
