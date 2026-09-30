// frontend/src/components/knowledge/KnowledgeChangeView.tsx
//
// One change, in full (spec web-ui "Follow knowledge changes in Recent
// changes"): who and when, and every document it touched with its diff and a
// link to that document's History. A curation pass also offers Undo this
// pass, which asks first and undoes the whole pass — or, when a document it
// wrote has changed since, is refused and names that document. A pass already
// undone says so instead.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowLeft, Undo2 } from "lucide-react";

import { KnowledgeDiff } from "@/components/knowledge/KnowledgeDiff";
import { KnowledgeUndoPassDialog } from "@/components/knowledge/KnowledgeUndoPassDialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut, DocumentDiffOut } from "@/lib/api/knowledge";
import { changeSentence, undoneVersions, writerLabel } from "@/lib/knowledge/changes";
import { collectionOfPath, collectionPath, KNOWLEDGE_ROOT } from "@/lib/knowledge/routes";
import { parseUnifiedDiff } from "@/lib/knowledge/unifiedDiff";
import { useKnowledgeChange, useKnowledgeChanges } from "@/lib/hooks/useKnowledgeHistory";
import { formatDateTime } from "@/lib/utils";

interface Props {
  version: string;
  collections: CollectionOut[];
}

const STATUS_SIGN: Record<DocumentDiffOut["status"], string> = {
  added: "+",
  modified: "~",
  removed: "−",
};

export function KnowledgeChangeView({ version, collections }: Props) {
  const { t } = useTranslation();
  const detail = useKnowledgeChange(version);
  const timeline = useKnowledgeChanges(null);
  const [undoing, setUndoing] = useState(false);
  const uidOf = new Map(collections.map((c) => [c.name, c.uid]));

  const back = (
    <Link
      to={KNOWLEDGE_ROOT}
      className="inline-flex items-center gap-1 text-xs text-text-subtle hover:text-text"
    >
      <ArrowLeft className="size-3.5" aria-hidden /> {t("knowledge.recent.title")}
    </Link>
  );

  if (detail.isPending) {
    return (
      <div className="space-y-3" aria-busy>
        {back}
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (detail.error) {
    return (
      <div className="space-y-3">
        {back}
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, detail.error)}
        </p>
      </div>
    );
  }

  const { change, diffs } = detail.data;
  const isPass = change.operation === "pass";
  const undone = undoneVersions(timeline.data?.changes ?? []).has(change.version);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto pb-6">
      {back}
      <header className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1 space-y-0.5">
          <h2 className="text-lg font-bold">
            {isPass
              ? t("knowledge.pass.title", { when: formatDateTime(change.time) })
              : `${writerLabel(t, change)} · ${formatDateTime(change.time)}`}
          </h2>
          <p className="text-sm text-text-muted">{changeSentence(t, change)}</p>
        </div>
        {isPass && undone ? (
          <span className="rounded-sm bg-chip px-2 py-0.5 text-xs text-text-muted">
            {t("knowledge.pass.undone")}
          </span>
        ) : isPass ? (
          <Button variant="outline" size="sm" onClick={() => setUndoing(true)}>
            <Undo2 aria-hidden /> {t("knowledge.pass.undo")}
          </Button>
        ) : null}
      </header>

      {diffs.map((d) => {
        const uid = uidOf.get(collectionOfPath(d.path));
        return (
          <section key={d.path} className="space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-mono text-xs text-text-subtle" aria-hidden>
                {STATUS_SIGN[d.status]}
              </span>
              <span className="font-mono text-xs">{d.path}</span>
              <span className="text-xs text-text-subtle">
                {t(`knowledge.pass.status.${d.status}`)}
              </span>
              <span className="text-xs tabular-nums">
                {d.added > 0 ? <span className="text-success">+{d.added}</span> : null}{" "}
                {d.removed > 0 ? <span className="text-danger">−{d.removed}</span> : null}
              </span>
              {uid && d.status !== "removed" ? (
                <Link
                  to={collectionPath(uid, "history", d.path)}
                  className="ml-auto text-xs text-accent-text hover:underline"
                >
                  {t("knowledge.history.tab")}
                </Link>
              ) : null}
            </div>
            <KnowledgeDiff rows={parseUnifiedDiff(d.diff)} />
          </section>
        );
      })}
      {isPass ? <p className="text-xs text-text-subtle">{t("knowledge.pass.itemsLeft")}</p> : null}

      <KnowledgeUndoPassDialog open={undoing} onOpenChange={setUndoing} change={change} />
    </div>
  );
}
