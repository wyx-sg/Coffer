// frontend/src/components/knowledge/KnowledgeStatsLine.tsx
//
// A collection's one status row (spec knowledge "Present a collection as one
// tree in the web UI"; board 5.1.13): *Documents N · Waiting M · Curated
// <time>*, each a small label over its value. Waiting
// links to the Inbox; while a Curate now run is draining it reads
// "Curating · n of m" instead of the curated time, straight from the daemon's
// in-flight list — no dialog, no toast. With Coffer's model not set nothing
// ever waits, so the line is Documents alone.
//
// "Curated" is the newest curation pass in the collection's own history, the
// same timeline Recent changes reads.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { CollectionOut } from "@/lib/api/knowledge";
import { timeAgo } from "@/lib/agents/hookRows";
import { collectionPath } from "@/lib/knowledge/routes";
import { curatingLabel } from "@/lib/knowledge/text";
import { useKnowledgeChanges } from "@/lib/hooks/useKnowledgeHistory";
import { useUpkeepRun } from "@/lib/hooks/useUpkeep";

interface Props {
  collection: CollectionOut;
  modelSet: boolean | undefined;
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="flex min-w-[110px] flex-col gap-0.5">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-lg font-bold tabular-nums text-text">{children}</span>
    </span>
  );
}

export function KnowledgeStatsLine({ collection, modelSet }: Props) {
  const { t, i18n } = useTranslation();
  const run = useUpkeepRun("knowledge", collection.uid);
  const changes = useKnowledgeChanges(collection.name);
  const lastPass = changes.data?.changes.find(
    (c) => c.writer === "curation" && c.operation === "pass",
  );

  return (
    <p className="flex flex-wrap items-center gap-x-7 gap-y-2" data-testid="knowledge-stats">
      <Stat label={t("knowledge.stats.documents")}>{collection.document_count}</Stat>
      {modelSet ? (
        <>
          <Stat label={t("knowledge.stats.waiting")}>
            <Link
              to={collectionPath(collection.uid, "inbox")}
              className="text-accent-text underline-offset-4 hover:underline"
            >
              {collection.pending_count}
            </Link>
          </Stat>
          <Stat label={t("knowledge.stats.curated")}>
            {run ? (
              <span className="text-sm font-book text-text-muted">{curatingLabel(t, run)}</span>
            ) : lastPass ? (
              timeAgo(lastPass.time, i18n.language)
            ) : (
              t("knowledge.stats.never")
            )}
          </Stat>
        </>
      ) : null}
    </p>
  );
}
