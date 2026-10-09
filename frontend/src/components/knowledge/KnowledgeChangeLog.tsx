// frontend/src/components/knowledge/KnowledgeChangeLog.tsx
//
// A collection's Change log (spec knowledge "Show a collection as one tree of
// read-only documents in the web UI", "Follow edits across collections in one
// feed"): the changes feed for this collection, newest first, one row per
// change — what it did, its writer and time, and the files it touched, each
// opening that file with its history drawer (`history=1`), where the change's
// diff and Restore are. Show more reads the next page while more are left.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChangeOut, CollectionOut } from "@/lib/api/knowledge";
import { useKnowledgeChangeLog } from "@/lib/hooks/useKnowledge";
import { operationLabel, whenLabel, writerLabel } from "@/lib/knowledge/changes";
import { collectionPath, pathInCollection } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
}

function ChangeRow({ change, uid }: { change: ChangeOut; uid: string }) {
  const { t, i18n } = useTranslation();
  return (
    <li className="flex flex-col gap-1 border-t border-border-subtle py-2.5 first:border-t-0">
      <div className="flex min-w-0 items-baseline gap-2">
        <span className="text-sm font-medium text-text">{operationLabel(t, change)}</span>
        <span className="truncate text-xs text-text-muted">
          {writerLabel(t, change)} · {whenLabel(t, change.time, i18n.language)}
        </span>
      </div>
      {change.documents.length > 0 ? (
        <ul className="flex flex-col gap-0.5">
          {change.documents.map((doc) => (
            <li key={doc.path} className="flex min-w-0 items-baseline gap-2 text-xs">
              <Link
                to={collectionPath(uid, doc.path, { history: true })}
                className="min-w-0 truncate font-mono text-text hover:underline"
              >
                {pathInCollection(doc.path)}
              </Link>
              <span className="shrink-0 font-mono text-text-muted">
                {t("knowledge.changeLog.lines", { added: doc.added, removed: doc.removed })}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function KnowledgeChangeLog({ collection }: Props) {
  const { t } = useTranslation();
  const log = useKnowledgeChangeLog(collection.name);

  let body;
  if (log.isLoading) {
    body = (
      <div className="space-y-2 py-2" aria-busy>
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  } else if (log.error) {
    body = (
      <LoadErrorRow
        title={t("knowledge.changeLog.failed")}
        error={log.error}
        onRetry={() => log.refetch()}
      />
    );
  } else if (log.items.length === 0) {
    body = <p className="py-2 text-sm text-text-muted">{t("knowledge.changeLog.none")}</p>;
  } else {
    body = (
      <>
        <ul aria-label={t("knowledge.changeLog.title")} className="flex flex-col">
          {log.items.map((change) => (
            <ChangeRow key={change.version} change={change} uid={collection.uid} />
          ))}
        </ul>
        {log.hasMore ? (
          <div className="pt-1">
            <Button
              variant="outline"
              size="sm"
              loading={log.isLoadingMore}
              onClick={() => log.loadMore()}
            >
              {t("knowledge.changeLog.more")}
            </Button>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <SettingsSection
      title={t("knowledge.changeLog.title")}
      description={t("knowledge.changeLog.description")}
      testId="knowledge-change-log"
    >
      {body}
    </SettingsSection>
  );
}
