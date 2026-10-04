// src/components/agents/sessions/AgentSessionsTab.tsx — spec agent-registry
// "Read one transcript session in bounded windows".
// The agent detail page's Sessions tab (boards 2.1.52–2.1.54): the agent's own
// CLI session history (Claude Code's ~/.claude/projects, Codex's
// ~/.codex/sessions), read-only. ONE bordered surface — the session list on
// the left (SessionList, newest first, search and a Project filter) and the
// open session on the right (SessionReader). The open session is in the URL as
// `?session=<source_path>` — the file, because `session_id` repeats across
// subagent sidechain files — so a reload or a link opens it again; none is
// opened until one is picked. Coffer never writes these files.
//
// No Refresh button: the lists read again when the window gets focus, and a
// session that moved after the list was read offers "Refresh list" itself.
import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";
import { useTranslation } from "react-i18next";

import { SessionList } from "@/components/agents/sessions/SessionList";
import { SessionReader } from "@/components/agents/sessions/SessionReader";
import { FileBrowserFrame } from "@/components/files/FileBrowserFrame";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { abbreviateHomePath, agentProgramName, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentTranscripts, useRefreshTranscripts } from "@/lib/hooks/useAgentTranscripts";

// One session is enough to know whether there are any at all.
const EXISTENCE_PROBE = 1;

export function AgentSessionsTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const selected = params.get("session");
  const recent = useAgentTranscripts(agent.uid, { limit: EXISTENCE_PROBE });
  const refresh = useRefreshTranscripts(agent.uid);
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
      <LoadErrorRow
        title={t("agents.sessionsTab.listFailed")}
        error={recent.error}
        onRetry={() => void refresh()}
      />
    );
  }
  if ((recent.data?.total ?? 0) === 0) {
    const dir = `${abbreviateHomePath(agent.config_dir)}/${agent.type === "codex" ? "sessions" : "projects"}`;
    return (
      <div className="rounded-xl border border-border px-6 py-8 text-center">
        <p className="text-sm font-semibold text-text">{t("agents.sessionsTab.emptyTitle")}</p>
        <p className="mt-1.5 text-xs text-text-muted">
          {t("agents.sessionsTab.emptyBody", {
            agent: agentName,
            dir,
            program: agentProgramName(agent.type),
          })}
        </p>
      </div>
    );
  }

  return (
    <FileBrowserFrame
      sideWidth={320}
      resizable={{
        storageKey: "agent-sessions",
        label: t("splitView.resizeList"),
        listMinWidth: 240,
        detailMinWidth: 480,
      }}
      side={<SessionList uid={agent.uid} selected={selected} onOpen={open} />}
      main={
        selected ? (
          <SessionReader
            key={selected}
            uid={agent.uid}
            sourcePath={selected}
            agentName={agentName}
            agentType={agent.type}
            onRefreshList={() => void refresh()}
          />
        ) : (
          <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-muted">
            {t("agents.sessionsTab.pick")}
          </div>
        )
      }
    />
  );
}
