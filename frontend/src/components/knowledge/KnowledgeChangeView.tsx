// frontend/src/components/knowledge/KnowledgeChangeView.tsx
//
// One change, in full (boards 5.1.18-5.1.20; spec web-ui "Follow knowledge
// changes in Recent changes"): the 15/600 title, one muted meta line — when,
// and for a pass "from 3 inbox items (2 from Claude Code, 1 from Codex)" — and
// every document it touched with its diff and a link to that document's
// History. A curation pass also offers Undo this pass, which asks first and
// undoes the whole pass. When a document it wrote has changed since, the daemon
// refuses the whole undo: the dialog closes and a notice above the documents
// names the one that changed, with a button to its History; Undo this pass
// stays on the bar. A pass already undone reads Undone, with when and by whom.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { CheckCircle2, Undo2 } from "lucide-react";

import { DiffLines } from "@/components/change-preview/FileDiff";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import { KnowledgeUndoPassDialog } from "@/components/knowledge/KnowledgeUndoPassDialog";
import { KnowledgeUndoRefusal } from "@/components/knowledge/KnowledgeUndoRefusal";
import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { ChangeOut, CollectionOut, DocumentDiffOut } from "@/lib/api/knowledge";
import { agentLabel, changeSentence, whenLabel, writerLabel } from "@/lib/knowledge/changes";
import { collectionOfPath, collectionPath, KNOWLEDGE_ROOT } from "@/lib/knowledge/routes";
import { undoRefusal } from "@/lib/knowledge/text";
import { parseUnifiedDiff } from "@/lib/knowledge/unifiedDiff";
import {
  useKnowledgeChange,
  useKnowledgeChanges,
  useUndoPass,
} from "@/lib/hooks/useKnowledgeHistory";
import { cn } from "@/lib/utils";

interface Props {
  version: string;
  collections: CollectionOut[];
}

const STATUS_SIGN: Record<DocumentDiffOut["status"], string> = {
  added: "+",
  modified: "~",
  removed: "−",
};

const STATUS_TONE: Record<DocumentDiffOut["status"], string> = {
  added: "bg-success-soft text-success",
  modified: "bg-chip text-text-muted",
  removed: "bg-danger-soft text-danger",
};

export function KnowledgeChangeView({ version, collections }: Props) {
  const { t, i18n } = useTranslation();
  const detail = useKnowledgeChange(version);
  const timeline = useKnowledgeChanges(null);
  const undo = useUndoPass();
  const [undoing, setUndoing] = useState(false);
  const uidOf = new Map(collections.map((c) => [c.name, c.uid]));

  const title = (change: ChangeOut | undefined) =>
    change
      ? change.operation === "pass"
        ? t("knowledge.pass.title", { when: whenLabel(t, change.time, i18n.language) })
        : `${writerLabel(t, change)} · ${whenLabel(t, change.time, i18n.language)}`
      : "";
  const crumbs = [
    { label: t("knowledge.recent.title"), to: KNOWLEDGE_ROOT, mono: true },
    { label: title(detail.data?.change), mono: true },
  ];

  if (!detail.data) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <KnowledgePaneBar crumbs={crumbs} />
        <div className="space-y-3 px-8 py-5">
          {detail.error ? (
            <p role="alert" className="text-sm text-danger">
              {translateApiError(t, detail.error)}
            </p>
          ) : (
            <div className="space-y-3" aria-busy>
              <Skeleton className="h-6 w-1/3" />
              <Skeleton className="h-32 w-full" />
            </div>
          )}
        </div>
      </div>
    );
  }

  const { change, diffs } = detail.data;
  const isPass = change.operation === "pass";
  const undoneBy = (timeline.data?.changes ?? []).find((c) => c.undoes === change.version);
  const refusal = undo.error ? undoRefusal(t, undo.error) : null;
  const changedSince = refusal?.document ?? null;
  const historyTo = (path: string | null) => {
    const uid = path ? uidOf.get(collectionOfPath(path)) : undefined;
    return path && uid ? collectionPath(uid, "history", path) : null;
  };

  const status = isPass ? (
    undoneBy ? (
      <span className="inline-flex h-[22px] items-center gap-1.5 rounded-item bg-chip px-2 text-xs font-semibold text-text-muted">
        {t("knowledge.pass.undone")}
      </span>
    ) : (
      <Button variant="outline" onClick={() => setUndoing(true)}>
        <Undo2 aria-hidden /> {t("knowledge.pass.undo")}
      </Button>
    )
  ) : null;

  // A pass names the agent whose inbox item it curated; the daemon records one
  // item per pass, so the breakdown is that agent's one.
  const from =
    isPass && change.agent
      ? t("knowledge.pass.fromItems", {
          count: 1,
          breakdown: t("knowledge.pass.fromAgent", {
            count: 1,
            agent: agentLabel(t, change.agent),
          }),
        })
      : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar crumbs={crumbs} actions={status} />
      <div className="min-h-0 flex-1 overflow-auto px-8 py-5">
        <div className="flex max-w-[820px] flex-col gap-3.5">
          <header className="flex items-start gap-3">
            <span className="pt-[3px]">
              <KnowledgeWriterMark writer={change.writer} agent={change.agent} />
            </span>
            <div className="flex min-w-0 flex-col gap-1">
              <h2 className="text-md font-semibold">
                {isPass ? t("knowledge.pass.heading") : changeSentence(t, change)}
              </h2>
              <p className="text-xs text-text-muted">
                {whenLabel(t, change.time, i18n.language)}
                {isPass ? (from ? ` · ${from}` : "") : ` · ${writerLabel(t, change)}`}
              </p>
            </div>
          </header>

          {undoneBy ? (
            <div
              role="status"
              className="flex items-start gap-2.5 rounded-lg border border-border bg-surface-sunken px-3 py-2.5"
            >
              <CheckCircle2 className="mt-px size-3.5 shrink-0 text-success" aria-hidden />
              <div className="flex flex-col gap-[3px]">
                <p className="text-sm font-label">
                  {t("knowledge.pass.undoneBy", {
                    who: writerLabel(t, undoneBy),
                    when: whenLabel(t, undoneBy.time, i18n.language),
                  })}
                </p>
                <p className="text-xs leading-[1.45] text-text-muted">
                  {t("knowledge.pass.undoneBody")}
                </p>
              </div>
            </div>
          ) : refusal ? (
            <KnowledgeUndoRefusal text={refusal.text} historyTo={historyTo(refusal.document)} />
          ) : null}

          <div className="flex flex-col">
            {diffs.map((d) => {
              const uid = uidOf.get(collectionOfPath(d.path));
              const docChange = change.documents.find((x) => x.path === d.path);
              return (
                <section
                  key={d.path}
                  className="flex flex-col gap-2 border-t border-border-subtle py-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {uid && d.status !== "removed" ? (
                      <Link
                        to={collectionPath(uid, "document", d.path)}
                        className="font-mono text-xs font-medium text-accent-text"
                      >
                        {d.path}
                      </Link>
                    ) : (
                      <span className="font-mono text-xs font-medium">{d.path}</span>
                    )}
                    <span
                      className={cn(
                        "inline-flex h-5 items-center gap-1 rounded-sm px-1.5 text-2xs font-label",
                        STATUS_TONE[d.status],
                      )}
                    >
                      <span className="font-mono font-medium">{STATUS_SIGN[d.status]}</span>
                      {t(`knowledge.pass.status.${d.status}`)}
                    </span>
                    {changedSince === d.path ? (
                      <span className="text-xs text-warning">
                        {t("knowledge.pass.changedSince")}
                      </span>
                    ) : null}
                    <span className="ml-auto flex items-center gap-2.5">
                      <span className="flex gap-1.5 font-mono text-2xs">
                        {(docChange?.added ?? d.added) > 0 ? (
                          <span className="text-success">+{docChange?.added ?? d.added}</span>
                        ) : null}
                        {(docChange?.removed ?? d.removed) > 0 ? (
                          <span className="text-danger">−{docChange?.removed ?? d.removed}</span>
                        ) : null}
                      </span>
                      {uid && d.status !== "removed" ? (
                        <Link
                          to={collectionPath(uid, "history", d.path)}
                          className="text-xs font-label text-text-muted hover:text-text"
                        >
                          {t("knowledge.history.tab")}
                        </Link>
                      ) : null}
                    </span>
                  </div>
                  {refusal ? null : <DiffLines lines={parseUnifiedDiff(d.diff)} />}
                </section>
              );
            })}
          </div>
        </div>
      </div>

      <KnowledgeUndoPassDialog
        open={undoing}
        onOpenChange={setUndoing}
        change={change}
        undo={undo}
      />
    </div>
  );
}
