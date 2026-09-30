// frontend/src/components/knowledge/KnowledgeWaitingList.tsx
//
// Recent changes' "Waiting to be curated": every item still in an inbox,
// across the collections shown, with who wrote it and when, each opening in
// its collection's Inbox — and the quiet Curate now, which curates each
// collection with items waiting, one after another (spec knowledge "Run
// curation on a sweep and on demand").
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { CollectionOut, WaitingItemOut } from "@/lib/api/knowledge";
import { agentLabel } from "@/lib/knowledge/changes";
import { collectionPath } from "@/lib/knowledge/routes";
import { useCurateCollections } from "@/lib/hooks/useKnowledge";
import { formatDateTime } from "@/lib/utils";

interface Props {
  waiting: WaitingItemOut[];
  collections: CollectionOut[];
}

export function KnowledgeWaitingList({ waiting, collections }: Props) {
  const { t } = useTranslation();
  const curate = useCurateCollections();
  const uidOf = new Map(collections.map((c) => [c.name, c.uid]));
  const targets = [...new Set(waiting.map((w) => uidOf.get(w.collection)))].filter(
    (u): u is string => Boolean(u),
  );

  return (
    <section
      className="space-y-2 rounded-md border border-border-subtle p-3"
      aria-label={t("knowledge.recent.waitingTitle")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{t("knowledge.recent.waitingTitle")}</h3>
        {waiting.length > 0 ? (
          <span className="text-xs text-text-subtle">
            {t("knowledge.recent.waitingCount", { count: waiting.length })} ·{" "}
            {t("knowledge.inbox.automatic")}
          </span>
        ) : null}
        {waiting.length > 0 ? (
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            disabled={curate.isPending}
            onClick={() => curate.mutate(targets)}
          >
            <Sparkles aria-hidden />
            {curate.isPending ? t("knowledge.curate.running") : t("knowledge.curate.now")}
          </Button>
        ) : null}
      </div>
      {waiting.length === 0 ? (
        <p className="text-xs text-text-subtle">{t("knowledge.recent.nothingWaiting")}</p>
      ) : (
        <ul className="space-y-1">
          {waiting.map((w) => {
            const uid = uidOf.get(w.collection);
            return (
              <li key={w.path} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                {uid ? (
                  <Link
                    to={collectionPath(uid, "inbox", w.path)}
                    className="truncate font-medium hover:underline"
                  >
                    {w.title}
                  </Link>
                ) : (
                  <span className="truncate font-medium">{w.title}</span>
                )}
                <span className="text-xs text-text-subtle">
                  {t("knowledge.recent.waitingMeta", {
                    collection: w.collection,
                    who: agentLabel(t, w.submitted_by),
                    when: formatDateTime(w.submitted_at),
                  })}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
