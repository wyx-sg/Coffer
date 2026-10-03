// frontend/src/components/knowledge/KnowledgeInboxView.tsx
//
// A collection's Inbox (boards 5.1.15, 5.1.16): the items waiting to be
// curated, and the one quiet Curate now (spec knowledge "Present a collection
// as one tree in the web UI"). Items are submitted by agents (`coffer__write`)
// and by uploads; curation files each into the right document on its own
// within the hour, so the button is only for "now". The list is a title, one
// muted line saying what happens to items, and rows that open whole (›). An
// item opens read-only — it is not a document yet — Reader-style: who wrote it
// and when, its title, its text; the bar says Read-only and holds Curate now.
// There is no edit and no delete. While a run is in flight Curate now reads
// "Curating · 1 of 2", no dialog.
//
// With Coffer's model not set there is no Inbox: items become documents as
// they arrive. The tree shows no Inbox node then, and an old link here says so.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Inbox, Lock } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { KnowledgeCurateNow } from "@/components/knowledge/KnowledgeCurateNow";
import { KnowledgeNoModelLine } from "@/components/knowledge/KnowledgeNoModelLine";
import { KnowledgePaneBar, type Crumb } from "@/components/knowledge/KnowledgePaneBar";
import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { timeAgo } from "@/lib/timeAgo";
import { agentLabel } from "@/lib/knowledge/changes";
import { collectionPath } from "@/lib/knowledge/routes";
import { useKnowledgeFile, useKnowledgeTree } from "@/lib/hooks/useKnowledge";

interface Props {
  collection: CollectionOut;
  /** An item open in the view, if any. */
  file: string | null;
  modelSet: boolean | undefined;
}

export function KnowledgeInboxView({ collection, file, modelSet }: Props) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const items = useKnowledgeTree(`${collection.name}/.inbox`, modelSet !== false);

  const crumbs: Crumb[] = [
    { label: collection.name, to: collectionPath(collection.uid), mono: true },
    { label: t("knowledge.inbox.title"), to: collectionPath(collection.uid, "inbox") },
    ...(file ? [{ label: file.split("/").pop() ?? file, mono: true }] : []),
  ];

  if (modelSet === false) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <KnowledgePaneBar crumbs={crumbs} />
        <div className="px-10 py-6">
          <KnowledgeNoModelLine />
        </div>
      </div>
    );
  }

  const rows = items.data?.files ?? [];
  const curate = <KnowledgeCurateNow collectionUid={collection.uid} variant="outline" icon={false} />;

  if (file) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <KnowledgePaneBar
          crumbs={crumbs}
          actions={
            <>
              <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
                <Lock className="size-3" aria-hidden />
                {t("knowledge.inbox.readOnlyTag")}
              </span>
              {curate}
            </>
          }
        />
        <div className="flex min-h-0 flex-1 flex-col overflow-auto px-8 py-7">
          <InboxItem path={file} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar crumbs={crumbs} />
      <div className="min-h-0 flex-1 overflow-auto px-8 py-7">
        <div className="mx-auto flex max-w-[720px] flex-col gap-3">
          <div className="flex flex-col gap-1">
            <h2 className="text-md font-semibold">{t("knowledge.inbox.title")}</h2>
            <div className="flex min-h-[26px] flex-wrap items-center gap-2">
              <span className="text-xs text-text-muted">{t("knowledge.inbox.note")}</span>
              {rows.length > 0 ? <span className="ml-auto">{curate}</span> : null}
            </div>
          </div>
          {items.isPending ? (
            <Skeleton className="h-16 w-full" />
          ) : items.error ? (
            <p role="alert" className="text-sm text-danger">
              {translateApiError(t, items.error)}
            </p>
          ) : rows.length === 0 ? (
            <EmptyState icon={Inbox} title={t("knowledge.inbox.empty")} />
          ) : (
            <ul className="divide-y divide-border-subtle overflow-hidden rounded-lg border border-border bg-surface-raised">
              {rows.map((item) => (
                <li key={item.path}>
                  <button
                    type="button"
                    aria-label={t("knowledge.recent.openItem", { title: item.title })}
                    onClick={() => navigate(collectionPath(collection.uid, "inbox", item.path))}
                    className="flex min-h-[52px] w-full items-center gap-2.5 px-3.5 py-2 text-left hover:bg-surface-sunken"
                  >
                    <KnowledgeWriterMark
                      writer={item.actor === "user" ? "user" : "agent"}
                      agent={item.actor}
                    />
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate text-sm">{item.title}</span>
                      <span className="truncate text-xs text-text-muted">
                        {t("knowledge.inbox.writtenBy", {
                          who: agentLabel(t, item.actor),
                          when: timeAgo(item.updated_at, i18n.language),
                        })}
                      </span>
                    </span>
                    <ChevronRight className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function InboxItem({ path }: { path: string }) {
  const { t, i18n } = useTranslation();
  const item = useKnowledgeFile(path);
  if (item.isPending) return <Skeleton className="mx-auto h-24 w-full max-w-[720px]" />;
  if (item.error) {
    return (
      <p role="alert" className="mx-auto w-full max-w-[720px] text-sm text-danger">
        {translateApiError(t, item.error)}
      </p>
    );
  }
  const byUser = item.data.actor === "user";
  const written = t(byUser ? "knowledge.inbox.writtenByYou" : "knowledge.inbox.writtenWithWrite", {
    who: agentLabel(t, item.data.actor),
    when: timeAgo(item.data.created_at, i18n.language),
  });
  return (
    <article className="mx-auto flex min-h-0 w-full max-w-[720px] flex-1 flex-col gap-3">
      <p className="flex shrink-0 items-center gap-2 text-xs text-text-muted">
        <KnowledgeWriterMark writer={byUser ? "user" : "agent"} agent={item.data.actor} />
        {`${written} · ${t("knowledge.inbox.waitingToCurate")}`}
      </p>
      <h1 className="shrink-0 text-xl font-bold leading-tight">{item.data.title}</h1>
      <div className="flex min-h-0 flex-1 flex-col">
        <FindableMarkdown fill>{item.data.body}</FindableMarkdown>
      </div>
    </article>
  );
}
