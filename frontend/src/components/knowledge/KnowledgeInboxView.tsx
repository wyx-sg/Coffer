// frontend/src/components/knowledge/KnowledgeInboxView.tsx
//
// A collection's Inbox: the items waiting to be curated, and the one quiet
// Curate now (spec knowledge "Present a collection as one tree in the web
// UI"). Items are submitted by agents (`coffer__write`), uploads and Add a
// document; curation files each into the right document on its own within the
// hour, so the button is only for "now". An item opens read-only — it is not
// a document yet — with who wrote it and when; there is no edit and no delete.
//
// With Coffer's model not set there is no Inbox: items become documents as
// they arrive, and the view says so rather than offering a trigger.
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Inbox } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { KnowledgeCurateNow } from "@/components/knowledge/KnowledgeCurateNow";
import { KnowledgeNoModelLine } from "@/components/knowledge/KnowledgeNoModelLine";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { agentLabel } from "@/lib/knowledge/changes";
import { collectionPath } from "@/lib/knowledge/routes";
import { useKnowledgeFile, useKnowledgeTree } from "@/lib/hooks/useKnowledge";
import { formatDateTime } from "@/lib/utils";

interface Props {
  collection: CollectionOut;
  /** An item open in the view, if any. */
  file: string | null;
  modelSet: boolean | undefined;
}

export function KnowledgeInboxView({ collection, file, modelSet }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const items = useKnowledgeTree(`${collection.name}/.inbox`, modelSet !== false);

  const header = (
    <header className="flex shrink-0 flex-wrap items-center gap-3">
      <div className="min-w-0 flex-1 space-y-0.5">
        <h2 className="flex items-center gap-2 text-lg font-bold">
          <Inbox className="size-4 text-text-subtle" aria-hidden />
          {t("knowledge.inbox.title")}
        </h2>
        <p className="text-xs text-text-subtle">{t("knowledge.inbox.hint")}</p>
      </div>
      {modelSet ? <KnowledgeCurateNow collectionUid={collection.uid} /> : null}
    </header>
  );

  if (modelSet === false) {
    return (
      <div className="space-y-4">
        {header}
        <KnowledgeNoModelLine />
      </div>
    );
  }

  if (file) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        {header}
        <Link
          to={collectionPath(collection.uid, "inbox")}
          className="inline-flex shrink-0 items-center gap-1 text-xs text-text-subtle hover:text-text"
        >
          <ArrowLeft className="size-3.5" aria-hidden /> {t("knowledge.inbox.back")}
        </Link>
        <InboxItem path={file} />
      </div>
    );
  }

  const rows = items.data?.files ?? [];
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {header}
      {items.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : items.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, items.error)}
        </p>
      ) : rows.length === 0 ? (
        <EmptyState icon={Inbox} title={t("knowledge.inbox.empty")} />
      ) : (
        <ul className="min-h-0 divide-y divide-border-subtle overflow-auto rounded-md border border-border-subtle">
          {rows.map((item) => (
            <li key={item.path}>
              <button
                type="button"
                onClick={() => navigate(collectionPath(collection.uid, "inbox", item.path))}
                className="w-full space-y-0.5 px-3 py-2 text-left hover:bg-surface-hover"
              >
                <p className="truncate text-sm font-medium">{item.title}</p>
                <p className="truncate text-xs text-text-subtle">
                  {t("knowledge.inbox.writtenBy", {
                    who: agentLabel(t, item.actor),
                    when: formatDateTime(item.updated_at),
                  })}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function InboxItem({ path }: { path: string }) {
  const { t } = useTranslation();
  const item = useKnowledgeFile(path);
  if (item.isPending) return <Skeleton className="h-24 w-full" />;
  if (item.error) {
    return (
      <p role="alert" className="text-sm text-danger">
        {translateApiError(t, item.error)}
      </p>
    );
  }
  return (
    <article className="flex min-h-0 flex-1 flex-col gap-2">
      <p className="shrink-0 text-xs text-text-subtle">
        {t("knowledge.inbox.waitingSince", {
          who: agentLabel(t, item.data.actor),
          when: formatDateTime(item.data.created_at),
        })}
      </p>
      <div className="min-h-0 flex-1 overflow-auto">
        <FindableMarkdown fill>{item.data.body}</FindableMarkdown>
      </div>
      <p className="shrink-0 text-xs text-text-subtle">{t("knowledge.inbox.readOnly")}</p>
    </article>
  );
}
