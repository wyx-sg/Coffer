// src/components/agents/sessions/AgentSessionsTab.tsx — spec agent-registry
// "Read one transcript session in bounded windows".
// The agent detail page's Sessions tab: the agent's own CLI session history
// (Claude Code's ~/.claude/projects, Codex's ~/.codex/sessions), read-only.
// A resizable split of the session list (SessionList) and the open session
// (SessionReader). The open session is in the URL as `?session=<source_path>`
// — the file, because `session_id` repeats across subagent sidechain files —
// so a reload or a link opens it again; none is opened until one is picked.
// Coffer never writes these files.
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MessagesSquare } from "lucide-react";

import { SessionList } from "@/components/agents/sessions/SessionList";
import { SessionReader } from "@/components/agents/sessions/SessionReader";
import { EmptyState } from "@/components/EmptyState";
import { useFillToBottom } from "@/components/filePane";
import { SplitView } from "@/components/SplitView";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentProgramName, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { useAgentTranscripts, useRefreshTranscripts } from "@/lib/hooks/useAgentTranscripts";

// The most recent sessions, read once: whether there are any at all, and the
// projects the filter offers (those seen in this window).
const PROJECT_SAMPLE = 100;

export function AgentSessionsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const selected = params.get("session");
  const recent = useAgentTranscripts(agent.uid, { limit: PROJECT_SAMPLE });
  const refresh = useRefreshTranscripts(agent.uid);
  const fill = useFillToBottom();
  const agentName = agentTypeLabel(agent.type);

  const open = (sourcePath: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("session", sourcePath);
      return next;
    });

  if (recent.isPending) {
    return <p className="text-sm text-text-muted">{t("common.loading")}</p>;
  }
  if (recent.error) {
    return (
      <EmptyState
        icon={MessagesSquare}
        tone="error"
        title={t("agents.sessionsTab.listFailed")}
        description={translateApiError(t, recent.error)}
        action={
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            {t("common.retry")}
          </Button>
        }
      />
    );
  }
  if ((recent.data?.total ?? 0) === 0) {
    const dir = `${abbreviateHomePath(agent.config_dir)}/${agent.type === "codex" ? "sessions" : "projects"}`;
    return (
      <EmptyState
        icon={MessagesSquare}
        title={t("agents.sessionsTab.emptyTitle")}
        description={t("agents.sessionsTab.emptyBody", {
          agent: agentName,
          dir,
          program: agentProgramName(agent.type),
        })}
        action={
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            {t("agents.sessionsTab.refresh")}
          </Button>
        }
      />
    );
  }

  const projects = [
    ...new Set(
      (recent.data?.sessions ?? []).flatMap((s) => (s.project_path ? [s.project_path] : [])),
    ),
  ].sort();

  return (
    <div ref={fill.ref} style={fill.style} className="flex min-h-0">
      <SplitView
        storageKey="agent-sessions"
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1"
        detailClassName="pl-4"
        list={<SessionList uid={agent.uid} projects={projects} selected={selected} onOpen={open} />}
        detail={
          selected ? (
            <SessionReader
              key={selected}
              uid={agent.uid}
              sourcePath={selected}
              agentName={agentName}
              onRefreshList={() => void refresh()}
            />
          ) : (
            <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed text-sm text-text-muted">
              {t("agents.sessionsTab.pick")}
            </div>
          )
        }
      />
    </div>
  );
}
