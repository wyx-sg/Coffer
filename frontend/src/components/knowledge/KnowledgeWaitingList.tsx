// frontend/src/components/knowledge/KnowledgeWaitingList.tsx
//
// Recent changes' "Waiting to be curated" (boards 5.1.07, 5.1.22): every item
// still in an inbox, across the collections shown, as one card of rows — who
// wrote it, its title, its collection and when — each opening read-only in its
// collection's Inbox, and the quiet Curate now, which curates each collection
// with items waiting, one after another (spec knowledge "Run curation on a
// sweep and on demand"). While a run is in flight the count reads
// "Curating · 1 of 2" from the daemon's in-flight list — no dialog.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";

import { Section } from "@/components/Section";
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

export function KnowledgeWaitingList({ waiting, collections }: Props) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const curate = useCurateCollections();
  const uidOf = new Map(collections.map((c) => [c.name, c.uid]));
  const targets = [...new Set(waiting.map((w) => uidOf.get(w.collection)))].filter(
    (u): u is string => Boolean(u),
  );
  const runs = useUpkeepRunsOf("knowledge");
  const run = runs.find((r) => targets.includes(r.name)) ?? null;
  const busy = run !== null || curate.isPending;

  return (
    <Section
      title={t("knowledge.recent.waitingTitle")}
      help={t("knowledge.inbox.automatic")}
      gap="snug"
      labelled
      aside={
        busy ? <span className="text-xs text-text-subtle">{curatingLabel(t, run)}</span> : null
      }
      actions={
        waiting.length > 0 && !busy ? (
          <Button variant="ghost" size="sm" onClick={() => curate.mutate(targets)}>
            <Sparkles aria-hidden />
            {t("knowledge.curate.now")}
          </Button>
        ) : null
      }
    >
      {waiting.length === 0 ? (
        <p className="text-xs text-text-subtle">{t("knowledge.recent.nothingWaiting")}</p>
      ) : (
        <ul className="divide-y divide-border-subtle">
          {waiting.map((w) => {
            const uid = uidOf.get(w.collection);
            const writer = w.submitted_by === "user" ? "user" : "agent";
            return (
              <li key={w.path} className="flex min-h-[52px] items-center gap-2.5 px-3.5 py-2">
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
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label={t("knowledge.recent.openItem", { title: w.title })}
                    onClick={() => navigate(collectionPath(uid, "inbox", w.path))}
                  >
                    {t("knowledge.recent.open")}
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
