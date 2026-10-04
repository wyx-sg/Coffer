// frontend/src/components/knowledge/KnowledgeWaitingList.tsx
//
// Recent changes' "Waiting to be curated" (boards 5.1.21–5.1.23): every item
// still in an inbox, across the collections shown, as one card of rows — who
// wrote it, its title, its collection and when — each row opening the item
// read-only in its collection's Inbox (the whole row is the link, › at its
// end), and the quiet Curate now, which curates each collection with items
// waiting, one after another (spec knowledge "Run curation on a sweep and on
// demand"). No count: the rows are the answer. While a run is in flight the
// section reads "Curating · 1 of 2" from the daemon's in-flight list — no
// dialog. With nothing waiting the section is its title and one grey line.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { Button } from "@/components/ui/button";
import type { CollectionOut, WaitingItemOut } from "@/lib/api/knowledge";
import { timeAgo } from "@/lib/timeAgo";
import { agentLabel } from "@/lib/knowledge/changes";
import { collectionPath } from "@/lib/knowledge/routes";
import { curatingLabel } from "@/lib/knowledge/text";
import { useCurateCollections } from "@/lib/hooks/useKnowledge";
import { useUpkeepRunsOf } from "@/lib/hooks/useUpkeep";

interface Props {
  waiting: WaitingItemOut[];
  collections: CollectionOut[];
}

const ROW = "flex min-h-[52px] items-center gap-2.5 px-3.5 py-2";

export function KnowledgeWaitingList({ waiting, collections }: Props) {
  const { t, i18n } = useTranslation();
  const curate = useCurateCollections();
  const uidOf = new Map(collections.map((c) => [c.name, c.uid]));
  const targets = [...new Set(waiting.map((w) => uidOf.get(w.collection)))].filter(
    (u): u is string => Boolean(u),
  );
  const runs = useUpkeepRunsOf("knowledge");
  const run = runs.find((r) => targets.includes(r.name)) ?? null;
  const busy = run !== null || curate.isPending;

  return (
    <section aria-label={t("knowledge.recent.waitingTitle")} className="flex flex-col gap-2">
      <div className="flex min-h-control-sm items-center gap-2">
        <h3 className="text-sm font-semibold text-text">{t("knowledge.recent.waitingTitle")}</h3>
        {waiting.length > 0 ? (
          <span className="text-xs text-text-muted">
            {busy ? curatingLabel(t, run) : t("knowledge.recent.waitingDesc")}
          </span>
        ) : null}
        {waiting.length > 0 && !busy ? (
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => curate.mutate(targets)}
          >
            {t("knowledge.curate.now")}
          </Button>
        ) : null}
      </div>
      {waiting.length === 0 ? (
        <p className="text-sm text-text-muted">{t("knowledge.recent.nothingWaiting")}</p>
      ) : (
        <ul className="divide-y divide-border-subtle overflow-hidden rounded-lg border border-border bg-surface-raised">
          {waiting.map((w) => {
            const uid = uidOf.get(w.collection);
            const writer = w.submitted_by === "user" ? "user" : "agent";
            const body = (
              <>
                <KnowledgeWriterMark writer={writer} agent={w.submitted_by} />
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-sm">{w.title}</span>
                  <span className="truncate text-xs text-text-muted">
                    {t("knowledge.recent.waitingMeta", {
                      collection: w.collection,
                      who: agentLabel(t, w.submitted_by),
                      when: timeAgo(w.submitted_at, i18n.language),
                    })}
                  </span>
                </div>
                {uid ? (
                  <ChevronRight className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
                ) : null}
              </>
            );
            return (
              <li key={w.path}>
                {uid ? (
                  <Link
                    to={collectionPath(uid, "inbox", w.path)}
                    className={`${ROW} text-text transition-colors duration-fast hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none`}
                  >
                    {body}
                  </Link>
                ) : (
                  <div className={ROW}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
