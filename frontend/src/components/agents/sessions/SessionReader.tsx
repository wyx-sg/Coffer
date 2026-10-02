// src/components/agents/sessions/SessionReader.tsx — spec agent-registry
// "Read one transcript session in bounded windows".
// The open session beside the Sessions list: its title, "<project> · <time
// range> · N messages", Open file, and the turns — a contents list of the
// person's own prompts (AgentTranscriptOutline) beside the conversation
// (AgentTranscriptView) — one bounded window at a time, paged with Earlier /
// Later turns. The whole file is never fetched at once.
//
// A file that moved or was deleted after the list was read fails to load; the
// reader says so in place and offers a retry and a fresh list.
import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentTranscriptOutline } from "@/components/agents/AgentTranscriptOutline";
import { AgentTranscriptView } from "@/components/agents/AgentTranscriptView";
import { projectName, timeRange } from "@/components/agents/sessions/sessionTime";
import { FileActions } from "@/components/FileActions";
import { Button } from "@/components/ui/button";
import { TruncatedPath, TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath } from "@/lib/agents/display";
import { TRANSCRIPT_TURNS_PAGE_SIZE, useTranscriptSession } from "@/lib/hooks/useAgentTranscripts";

function shortFile(path: string): string {
  const name = projectName(path) ?? path;
  return name.length > 24 ? `${name.slice(0, 4)}…${name.slice(-10)}` : name;
}

export function SessionReader({
  uid,
  sourcePath,
  agentName,
  onRefreshList,
}: {
  uid: string;
  sourcePath: string;
  agentName: string;
  onRefreshList: () => void;
}) {
  const { t } = useTranslation();
  const [offset, setOffset] = useState(0);
  const session = useTranscriptSession(uid, sourcePath, offset);
  const data = session.data;

  if (session.isPending) {
    return <p className="p-4 text-sm text-text-muted">{t("common.loading")}</p>;
  }
  if (session.error || !data) {
    return (
      <div
        role="alert"
        className="m-4 space-y-3 rounded-md border border-danger bg-danger-soft px-4 py-3"
      >
        <p className="text-sm font-medium text-danger">{t("agents.sessionsTab.loadFailed")}</p>
        <p className="text-xs text-text-muted">
          {t("agents.sessionsTab.loadFailedBody", { file: shortFile(sourcePath) })}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => void session.refetch()}>
            {t("agents.sessionsTab.tryAgain")}
          </Button>
          <Button size="sm" variant="outline" onClick={onRefreshList}>
            {t("agents.sessionsTab.refreshList")}
          </Button>
        </div>
      </div>
    );
  }

  const shown = data.messages.length;
  const hasMore = data.offset + shown < data.message_count;
  const meta = [
    data.project_path ? abbreviateHomePath(data.project_path) : null,
    timeRange(data.started_at, data.last_activity_at),
    t("agents.sessionsTab.messages", { count: data.message_count }),
  ].filter((part): part is string => Boolean(part));

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-md font-semibold text-text">
            <TruncatedText text={data.title ?? t("agents.sessionsTab.untitled")} />
          </h3>
          <p className="flex min-w-0 items-baseline gap-x-1.5 text-xs text-text-muted">
            {meta.map((part, i) => (
              <Fragment key={part}>
                {i > 0 ? <span aria-hidden>·</span> : null}
                {i === 0 && data.project_path ? (
                  <span className="min-w-0">
                    <TruncatedPath text={part} />
                  </span>
                ) : (
                  <span className="shrink-0 whitespace-nowrap">{part}</span>
                )}
              </Fragment>
            ))}
          </p>
        </div>
        <FileActions filePath={data.source_path} />
      </div>
      {shown > 0 ? (
        <p className="shrink-0 text-2xs text-text-subtle">
          {t("agents.sessionsTab.turnRange", {
            from: data.offset + 1,
            to: data.offset + shown,
            total: data.message_count,
          })}
        </p>
      ) : null}
      <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[14rem_minmax(0,1fr)]">
        <AgentTranscriptOutline messages={data.messages} offset={data.offset} />
        <AgentTranscriptView messages={data.messages} agentName={agentName} />
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {offset > 0 || hasMore ? (
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - TRANSCRIPT_TURNS_PAGE_SIZE))}
            >
              {t("agents.sessionsTab.earlier")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasMore}
              onClick={() => setOffset((o) => o + TRANSCRIPT_TURNS_PAGE_SIZE)}
            >
              {t("agents.sessionsTab.later")}
            </Button>
          </>
        ) : null}
        <span className="ml-auto text-2xs text-text-subtle">
          {t("agents.sessionsTab.readOnly")}
        </span>
      </div>
    </div>
  );
}
