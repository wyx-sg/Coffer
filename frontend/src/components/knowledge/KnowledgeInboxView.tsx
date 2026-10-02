// frontend/src/components/knowledge/KnowledgeInboxView.tsx
//
// A collection's Inbox (boards 5.1.09, 5.1.26): the items waiting to be
// curated, and the one quiet Curate now (spec knowledge "Present a collection
// as one tree in the web UI"). Items are submitted by agents
// (`coffer__write`), uploads and Add a document; curation files each into the
// right document on its own within the hour, so the button is only for
// "now". An item opens read-only — it is not a document yet — with who wrote
// it and when; there is no edit and no delete. While a run is in flight the
// status reads "Curating · 1 of 2", no dialog.
//
// With Coffer's model not set there is no Inbox: items become documents as
// they arrive. The tree shows no Inbox node then, and an old link here says so.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Inbox } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { KnowledgeCurateNow } from "@/components/knowledge/KnowledgeCurateNow";
import { KnowledgeNoModelLine } from "@/components/knowledge/KnowledgeNoModelLine";
import { KnowledgePaneBar, type Crumb } from "@/components/knowledge/KnowledgePaneBar";
import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { timeAgo } from "@/lib/timeAgo";
import { agentLabel } from "@/lib/knowledge/changes";
import { collectionPath } from "@/lib/knowledge/routes";
import { curatingLabel } from "@/lib/knowledge/text";
import { useKnowledgeFile, useKnowledgeTree } from "@/lib/hooks/useKnowledge";
import { useUpkeepRun } from "@/lib/hooks/useUpkeep";

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
  const run = useUpkeepRun("knowledge", collection.uid);

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
  const status = (
    <div className="flex min-h-[26px] flex-wrap items-center gap-2">
      <span className="text-xs text-text-subtle">
        {run
          ? curatingLabel(t, run)
          : file
            ? t("knowledge.inbox.hint")
            : `${t("knowledge.recent.waitingCount", { count: rows.length })} · ${t("knowledge.inbox.automatic")}`}
      </span>
      {rows.length > 0 || file ? (
        <span className="ml-auto">
          <KnowledgeCurateNow collectionUid={collection.uid} />
        </span>
      ) : null}
    </div>
  );

  if (file) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <KnowledgePaneBar crumbs={crumbs} />
        <div className="flex min-h-0 flex-1 flex-col gap-4 px-10 pb-7 pt-[18px]">
          {status}
          <InboxItem path={file} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar crumbs={crumbs} />
      <div className="min-h-0 flex-1 overflow-auto px-8 pb-7 pt-5">
        <div className="flex max-w-[760px] flex-col gap-2">
          <h2 className="text-[16px] font-bold">
            {t("knowledge.inbox.heading", { name: collection.name })}
          </h2>
          {status}
          {items.isPending ? (
            <Skeleton className="h-16 w-full" />
          ) : items.error ? (
            <p role="alert" className="text-sm text-danger">
              {translateApiError(t, items.error)}
            </p>
          ) : rows.length === 0 ? (
            <EmptyState icon={Inbox} title={t("knowledge.inbox.empty")} />
          ) : (
            <>
              <ul className="divide-y divide-border-subtle overflow-hidden rounded-lg border border-border bg-surface-raised">
                {rows.map((item) => (
                  <li
                    key={item.path}
                    className="flex min-h-[52px] items-center gap-2.5 px-3.5 py-2"
                  >
                    <KnowledgeWriterMark
                      writer={item.actor === "user" ? "user" : "agent"}
                      agent={item.actor}
                    />
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate text-sm">{item.title}</span>
                      <span className="truncate text-xs text-text-muted">
                        {t("knowledge.inbox.writtenBy", {
                          who: agentLabel(t, item.actor),
                          when: timeAgo(item.updated_at, i18n.language),
                        })}
                      </span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      aria-label={t("knowledge.recent.openItem", { title: item.title })}
                      onClick={() => navigate(collectionPath(collection.uid, "inbox", item.path))}
                    >
                      {t("knowledge.recent.open")}
                    </Button>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-text-subtle">{t("knowledge.inbox.readOnly")}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function InboxItem({ path }: { path: string }) {
  const { t, i18n } = useTranslation();
  const item = useKnowledgeFile(path);
  if (item.isPending) return <Skeleton className="h-24 w-full" />;
  if (item.error) {
    return (
      <p role="alert" className="text-sm text-danger">
        {translateApiError(t, item.error)}
      </p>
    );
  }
  const byUser = item.data.actor === "user";
  return (
    <article className="flex min-h-0 max-w-[640px] flex-1 flex-col gap-3">
      <p className="flex shrink-0 items-center gap-2 text-xs text-text-muted">
        <KnowledgeWriterMark writer={byUser ? "user" : "agent"} agent={item.data.actor} />
        {t(byUser ? "knowledge.inbox.writtenByYou" : "knowledge.inbox.writtenWithWrite", {
          who: agentLabel(t, item.data.actor),
          when: timeAgo(item.data.created_at, i18n.language),
        })}
      </p>
      <h1 className="shrink-0 text-[22px] font-bold leading-tight tracking-[-0.01em]">
        {item.data.title}
      </h1>
      <div className="flex min-h-0 flex-1 flex-col">
        <FindableMarkdown fill>{item.data.body}</FindableMarkdown>
      </div>
    </article>
  );
}
