// src/components/agents/sessions/SessionReader.tsx — spec agent-registry
// "Read one transcript session in bounded windows".
// The open session beside the Sessions list (boards 2.1.52, 2.1.54): the
// viewer toolbar (the file's path, Open in editor, a Reveal icon), then the
// conversation in one column — the session's title and a meta line "<project> ·
// <time range> · N messages · Read-only" on top — one bounded window of turns
// at a time, paged with Earlier / Later turns in a footer. The whole file is
// never fetched at once.
//
// A file that moved or was deleted after the list was read fails to load; the
// reader says so in place, with Retry and a link that refreshes the list.
import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp } from "lucide-react";

import { AgentTranscriptView } from "@/components/agents/AgentTranscriptView";
import { timeRange } from "@/components/agents/sessions/sessionTime";
import { ViewerToolbar } from "@/components/files/ViewerToolbar";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import { TRANSCRIPT_TURNS_PAGE_SIZE, useTranscriptSession } from "@/lib/hooks/useAgentTranscripts";

/** `~/…/projects/-Users-x/7f3c9a…e91a.jsonl` → the id in the file name cut to its ends. */
function shownFile(sourcePath: string): string {
  const path = abbreviateHomePath(sourcePath);
  const cut = path.lastIndexOf("/");
  const name = path.slice(cut + 1);
  const dot = name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name;
  const short = stem.length > 12 ? `${stem.slice(0, 4)}…${stem.slice(-4)}` : stem;
  return `${path.slice(0, cut + 1)}${short}${dot > 0 ? name.slice(dot) : ""}`;
}

export function SessionReader({
  uid,
  sourcePath,
  agentName,
  agentType,
  onRefreshList,
}: {
  uid: string;
  sourcePath: string;
  agentName: string;
  agentType: string;
  onRefreshList: () => void;
}) {
  const { t } = useTranslation();
  const [offset, setOffset] = useState(0);
  const session = useTranscriptSession(uid, sourcePath, offset);
  const data = session.data;
  const toolbarPath = shownFile(sourcePath);

  if (session.isPending) {
    return (
      <>
        <ViewerToolbar path={toolbarPath} fullPath={sourcePath} />
        <p className="p-4 text-sm text-text-muted">{t("common.loading")}</p>
      </>
    );
  }
  if (session.error || !data) {
    return (
      <>
        <ViewerToolbar path={toolbarPath} fullPath={sourcePath} />
        <div className="px-8 py-6">
          <LoadErrorRow
            title={t("agents.sessionsTab.loadFailed")}
            reason={t("agents.sessionsTab.loadFailedBody")}
            onRetry={() => void session.refetch()}
            actions={
              <Button variant="link" size="sm" onClick={onRefreshList}>
                {t("agents.sessionsTab.refreshList")}
              </Button>
            }
          />
        </div>
      </>
    );
  }

  const shown = data.messages.length;
  const hasMore = data.offset + shown < data.message_count;
  const meta = [
    data.project_path ? abbreviateHomePath(data.project_path) : null,
    timeRange(data.started_at, data.last_activity_at),
    t("agents.sessionsTab.messages", { count: data.message_count }),
    t("agents.sessionsTab.readOnly"),
  ].filter((part): part is string => Boolean(part));

  const header = (
    <div className="mb-6">
      <h3 className="text-xl font-bold text-text">
        {data.title ?? t("agents.sessionsTab.untitled")}
      </h3>
      <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5 text-xs text-text-muted">
        {meta.map((part, i) => (
          <Fragment key={part}>
            {i > 0 ? <span aria-hidden>·</span> : null}
            <span className="min-w-0 break-all">{part}</span>
          </Fragment>
        ))}
      </p>
    </div>
  );

  return (
    <>
      <ViewerToolbar
        path={toolbarPath}
        fullPath={data.source_path}
        absPath={data.source_path}
        reveal
      />
      <AgentTranscriptView
        messages={data.messages}
        agentName={agentName}
        agentType={agentType}
        header={header}
      />
      {offset > 0 || hasMore ? (
        <div className="flex h-12 shrink-0 items-center gap-2 border-t border-border-subtle px-4">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - TRANSCRIPT_TURNS_PAGE_SIZE))}
          >
            <ChevronUp aria-hidden /> {t("agents.sessionsTab.earlier")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasMore}
            onClick={() => setOffset((o) => o + TRANSCRIPT_TURNS_PAGE_SIZE)}
          >
            <ChevronDown aria-hidden /> {t("agents.sessionsTab.later")}
          </Button>
          {shown > 0 ? (
            <span className="ml-auto text-xs text-text-muted">
              {t("agents.sessionsTab.turnRange", {
                from: data.offset + 1,
                to: data.offset + shown,
                total: data.message_count,
              })}
            </span>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
