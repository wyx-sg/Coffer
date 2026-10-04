// frontend/src/components/knowledge/KnowledgeHistoryTab.tsx
//
// A document's History (boards 5.1.05–5.1.08; spec web-ui "Show a knowledge
// document's history on its History tab"): the same card as a skill's History
// (VersionHistorySplit) filling the pane — the versions on the left, newest
// first, each with who wrote it (you, curation naming the agent whose item it
// curated, sync, an edit on disk), "when · one sentence of what it did" and the
// lines it moved in this document, the newest wearing a Current chip; on the
// right the chosen version's diff (KnowledgeVersionPanel) with Restore this
// version, which writes a NEW version naming you rather than rewriting the
// past, and, for a curation pass, "See the pass". The newest version is chosen
// when the tab opens. A history that cannot be read is one LoadErrorRow here;
// with git missing it is the neutral "History needs git" row carrying the
// daemon's install prompt. The Document tab reads on its own and keeps working.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { History } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { VersionHistorySplit } from "@/components/history/VersionHistorySplit";
import { KnowledgeVersionPanel } from "@/components/knowledge/KnowledgeVersionPanel";
import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { ApiError } from "@/lib/api/errors";
import { versionSentence, whenLabel, writerLabel } from "@/lib/knowledge/changes";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";

interface Props {
  path: string;
  /** The document's body as it is now — what Compare with current diffs against. */
  currentBody: string;
}

function isGitMissing(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return (error.details as { reason?: unknown } | undefined)?.reason === "git_missing";
}

export function KnowledgeHistoryTab({ path, currentBody }: Props) {
  const { t, i18n } = useTranslation();
  const history = useDocumentHistory(path);
  const [chosen, setChosen] = useState<string | null>(null);

  let content;
  if (history.isPending) {
    content = (
      <div className="space-y-2" aria-busy>
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-3/5" />
      </div>
    );
  } else if (history.error) {
    const prompt = errorHandoff(history.error);
    content = isGitMissing(history.error) ? (
      <LoadErrorRow
        tone="neutral"
        title={t("knowledge.history.needsGitTitle")}
        reason={t("knowledge.history.needsGitBody")}
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => void history.refetch()}>
              {t("knowledge.history.checkAgain")}
            </Button>
            {prompt ? <AgentHandoff size="sm" help={false} prompt={prompt} /> : null}
          </>
        }
      />
    ) : (
      <LoadErrorRow
        title={t("knowledge.history.failedTitle")}
        error={history.error}
        onRetry={() => void history.refetch()}
        actions={
          <Link
            to="/activity"
            className="text-xs font-label text-accent-text hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            {t("knowledge.history.openActivity")}
          </Link>
        }
      />
    );
  } else if (history.data.versions.length === 0) {
    content = <EmptyState icon={History} title={t("knowledge.history.none")} />;
  } else {
    const versions = history.data.versions;
    const index = Math.max(
      0,
      versions.findIndex((v) => v.change.version === chosen),
    );
    const selected = versions[index];
    return (
      <div className="flex min-h-0 flex-1 flex-col px-8 py-5">
        <VersionHistorySplit
          storageKey="knowledge-history"
          versions={versions}
          getKey={(v) => v.change.version}
          selectedIndex={index}
          onSelect={(i) => setChosen(versions[i].change.version)}
          listLabel={t("knowledge.history.versions")}
          currentLabel={t("knowledge.history.current")}
          dividerLabel={t("splitView.resizeList")}
          renderRow={(v) => {
            const c = v.change;
            const doc = c.documents.find((d) => d.path === path);
            return {
              icon: <KnowledgeWriterMark writer={c.writer} agent={c.agent} />,
              title: writerLabel(t, c),
              subline: `${whenLabel(t, c.time, i18n.language)} · ${versionSentence(t, c)}`,
              trailing:
                doc && (doc.added || doc.removed)
                  ? `${doc.added ? `+${doc.added}` : ""}${doc.added && doc.removed ? " " : ""}${doc.removed ? `−${doc.removed}` : ""}`
                  : undefined,
            };
          }}
          detail={
            <KnowledgeVersionPanel
              key={selected.change.version}
              path={path}
              version={selected}
              isCurrent={index === 0}
              currentBody={currentBody}
            />
          }
        />
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto px-8 py-5">
      <div className="mx-auto max-w-[720px]">{content}</div>
    </div>
  );
}
