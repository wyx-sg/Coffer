// frontend/src/components/knowledge/KnowledgeHistoryTab.tsx
//
// A document's History (boards 5.1.05–5.1.08; spec web-ui "Show a knowledge
// document's history on its History tab"): ONE bordered list, newest first,
// 720 wide in the pane. A row is a chevron, who wrote the version (you,
// curation naming the agent whose item it curated, sync, an edit on disk),
// when, one sentence of what it did — a curation row ends in "See the pass" —
// and the lines it moved. A row opens in place into its diff
// (KnowledgeVersionPanel) with Restore this version, which writes a NEW
// version naming you rather than rewriting the past. A history that cannot be
// read is one LoadErrorRow here; with git missing it is the neutral "History
// needs git" row carrying the daemon's install prompt. The Document tab reads
// on its own and keeps working.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, History } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { KnowledgeVersionPanel } from "@/components/knowledge/KnowledgeVersionPanel";
import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorHandoff } from "@/lib/api/errorHandoff";
import { ApiError } from "@/lib/api/errors";
import { versionSentence, whenLabel, writerLabel } from "@/lib/knowledge/changes";
import { changePath } from "@/lib/knowledge/routes";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";
import { cn } from "@/lib/utils";

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
  const [open, setOpen] = useState<string | null>(null);

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
    content = (
      <div
        role="list"
        aria-label={t("knowledge.history.versions")}
        className="overflow-hidden rounded-lg border border-border bg-surface-raised"
      >
        {versions.map((v, i) => {
          const c = v.change;
          const expanded = open === c.version;
          const doc = c.documents.find((d) => d.path === path);
          return (
            <div
              key={c.version}
              role="listitem"
              className={cn(
                "border-border-subtle",
                i > 0 && "border-t",
                expanded && "bg-surface-sunken",
              )}
            >
              <div className="relative flex min-h-[52px] items-center gap-2.5 px-3.5">
                <span className="inline-flex text-text-subtle">
                  {expanded ? (
                    <ChevronDown className="size-3.5" aria-hidden />
                  ) : (
                    <ChevronRight className="size-3.5" aria-hidden />
                  )}
                </span>
                <KnowledgeWriterMark writer={c.writer} agent={c.agent} />
                <div className="flex min-w-0 flex-1 flex-col gap-0.5 py-2">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() => setOpen(expanded ? null : c.version)}
                    className="flex items-center gap-1.5 text-left outline-none after:absolute after:inset-0 hover:after:bg-surface-hover/40 focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-focus-ring"
                  >
                    <span className="text-sm font-label text-text">{writerLabel(t, c)}</span>
                    <span className="text-xs text-text-muted">
                      {whenLabel(t, c.time, i18n.language)}
                    </span>
                    {i === 0 ? (
                      <span className="inline-flex h-5 items-center rounded-sm bg-chip px-[7px] text-2xs font-label text-text-muted">
                        {t("knowledge.history.current")}
                      </span>
                    ) : null}
                  </button>
                  <p className="pointer-events-none truncate text-xs text-text-muted">
                    {versionSentence(t, c)}
                    {c.operation === "pass" ? (
                      <>
                        {" · "}
                        <Link
                          to={changePath(c.version)}
                          className="pointer-events-auto relative z-10 font-label text-accent-text hover:opacity-80"
                        >
                          {t("knowledge.history.seePass")}
                        </Link>
                      </>
                    ) : null}
                  </p>
                </div>
                {doc && (doc.added || doc.removed) ? (
                  <span className="pointer-events-none whitespace-nowrap font-mono text-2xs text-text-subtle">
                    {doc.added ? `+${doc.added}` : ""}
                    {doc.added && doc.removed ? " " : ""}
                    {doc.removed ? `−${doc.removed}` : ""}
                  </span>
                ) : null}
              </div>
              {expanded ? (
                <div className="pb-3.5 pl-[46px] pr-3.5 pt-1">
                  <KnowledgeVersionPanel
                    path={path}
                    version={v}
                    isCurrent={i === 0}
                    currentBody={currentBody}
                  />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto px-8 py-5">
      <div className="mx-auto max-w-[720px]">{content}</div>
    </div>
  );
}
