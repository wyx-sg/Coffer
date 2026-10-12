// frontend/src/components/knowledge/KnowledgeChangeLog.tsx
//
// A collection's Change log (spec knowledge "Follow edits across collections
// in one feed", "Record a tidy as one change", "Undo a tidy"): the changes
// feed for this collection, newest first, on a timeline.
//
// A tidy is one entry: the agent and its time, the agent's report (or that
// Coffer closed it without one, after its collection sat unchanged), the pages
// it touched by title — folded when there are many — and **Undo this tidy…**,
// which asks first and puts every file back as one new change; when a file was
// edited since, a second question names those files and offers Undo anyway.
// A run of edits made on disk within minutes of each other is one entry
// (lib/knowledge/changeGroups.ts). Any other change is its own entry. A file
// opens with its history (`history=1`), where each change's diff and Restore
// are. Show more reads the next page while more are left.
import { useTranslation } from "react-i18next";

import {
  ChangeEntry,
  ChangeFiles,
  type TitleOf,
} from "@/components/knowledge/KnowledgeChangeParts";
import { KnowledgeTidyEntry } from "@/components/knowledge/KnowledgeTidyEntry";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useKnowledgeChangeLog, useKnowledgeFiles } from "@/lib/hooks/useKnowledge";
import { groupChanges, groupDocuments, type ChangeGroup } from "@/lib/knowledge/changeGroups";
import { operationLabel, whenLabel, writerLabel } from "@/lib/knowledge/changes";
import { pathInCollection } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
}

function GroupEntry({
  group,
  uid,
  titleOf,
  undone,
}: {
  group: ChangeGroup;
  uid: string;
  titleOf: TitleOf;
  undone: Set<string>;
}) {
  const { t, i18n } = useTranslation();
  if (group.kind === "disk") {
    const newest = group.changes[0];
    const oldest = group.changes[group.changes.length - 1];
    const when =
      group.changes.length > 1
        ? t("knowledge.changeLog.span", {
            from: whenLabel(t, oldest.time, i18n.language),
            to: whenLabel(t, newest.time, i18n.language).replace(/^.* /, ""),
          })
        : whenLabel(t, newest.time, i18n.language);
    return (
      <ChangeEntry
        heading={operationLabel(t, newest)}
        meta={[
          writerLabel(t, newest),
          group.changes.length > 1
            ? t("knowledge.changeLog.saves", { count: group.changes.length })
            : null,
          when,
        ]
          .filter(Boolean)
          .join(" · ")}
      >
        <ChangeFiles documents={groupDocuments(group.changes)} uid={uid} titleOf={titleOf} />
      </ChangeEntry>
    );
  }
  const change = group.change;
  if (change.operation === "tidy") {
    return (
      <KnowledgeTidyEntry
        change={change}
        uid={uid}
        titleOf={titleOf}
        undone={undone.has(change.version)}
      />
    );
  }
  return (
    <ChangeEntry
      heading={change.undoes ? t("knowledge.changeLog.undid") : operationLabel(t, change)}
      meta={`${writerLabel(t, change)} · ${whenLabel(t, change.time, i18n.language)}`}
    >
      <ChangeFiles documents={groupDocuments([change])} uid={uid} titleOf={titleOf} />
    </ChangeEntry>
  );
}

export function KnowledgeChangeLog({ collection }: Props) {
  const { t } = useTranslation();
  const log = useKnowledgeChangeLog(collection.name);
  const files = useKnowledgeFiles(collection.uid);
  const titles = new Map((files.data ?? []).map((f) => [f.path, f.title]));
  const titleOf: TitleOf = (path) => titles.get(path) || pathInCollection(path);

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
    // A change some later change undid shows as undone, with no Undo of its own.
    const undone = new Set(log.items.map((c) => c.undoes).filter((v): v is string => !!v));
    body = (
      <>
        <ul aria-label={t("knowledge.changeLog.title")} className="flex flex-col pt-1">
          {groupChanges(log.items).map((group) => (
            <GroupEntry
              key={group.kind === "disk" ? group.changes[0].version : group.change.version}
              group={group}
              uid={collection.uid}
              titleOf={titleOf}
              undone={undone}
            />
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
