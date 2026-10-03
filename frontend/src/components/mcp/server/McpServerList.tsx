// src/components/mcp/server/McpServerList.tsx — the left pane of the MCP servers page (design 4.1.01).
//
// "Filter servers" (name, title and command or URL), then the servers grouped
// by what needs the user — Needs attention (failing, launcher missing, secret
// missing, each with its reason), Healthy, Not checked yet, Off — with a count
// each, then Built-in (Coffer's own `coffer` server, read-only). Search and Reach
// filter every row, the built-in one included. While rows are ticked the selection bar takes the filters' place
// at the top. Each row reads its own
// status and tiering (both cheap, persisted reads), so the grouping is done
// here from the cached answers the rows share.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentFilterPill } from "@/components/agents/tabs/AgentFilterPill";
import { ReachFilter } from "@/components/reach/ReachFilter";
import { SearchInput } from "@/components/SearchInput";
import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import type { ResourceOut } from "@/lib/api/resources";
import { useAgentFilter } from "@/lib/agents/agentFilter";
import { useAgents } from "@/lib/hooks/useAgents";
import { useBuiltinMcpServer } from "@/lib/hooks/useMcpAddFlow";
import { useMcpServerListReads } from "@/lib/hooks/useMcpServerPage";
import { matchesReach, type ReachFilterValue } from "@/lib/reachFilter";
import { McpBuiltinRow } from "./McpBuiltinRow";
import { McpServerListRow } from "./McpServerListRow";
import { McpServersBulkBar } from "./McpServersBulkBar";
import { GROUP_ORDER, serverState, transportOf, type ServerGroup } from "@/lib/mcp/serverState";

/** The fixed name of Coffer's own server, and its address on this page. */
export const BUILTIN_NAME = "coffer";

interface Props {
  servers: ResourceOut[];
  isLoading: boolean;
  /** The list read failed: the pane shows the error block under the filter. */
  error?: unknown;
  onRetry?: () => void;
  selectedName: string | null;
  hrefFor: (name: string) => string;
  /** The built-in `coffer` server is the open one. */
  builtinSelected?: boolean;
}

export function McpServerList({
  servers,
  isLoading,
  error,
  onRetry,
  selectedName,
  hrefFor,
  builtinSelected = false,
}: Props) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const [query, setQuery] = useState("");
  const [reach, setReach] = useState<ReachFilterValue>("all");
  const agentFilter = useAgentFilter();
  const { data: builtin } = useBuiltinMcpServer();
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());

  const { details, splits } = useMcpServerListReads(servers.map((s) => s.uid));
  const detailOf = (i: number) => details.get(servers[i].uid);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out = new Map<ServerGroup, number[]>(GROUP_ORDER.map((g) => [g, []]));
    servers.forEach((s, i) => {
      const haystack = `${s.name} ${s.title ?? ""} ${transportOf(s.config).target}`.toLowerCase();
      if (q && !haystack.includes(q)) return;
      if (!matchesReach(reach, s)) return;
      if (agentFilter && !agentFilter.matches(s)) return;
      out.get(serverState(s, detailOf(i)).group)?.push(i);
    });
    return out;
    // detailOf reads `details`, whose answers are what change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servers, query, reach, details, agentFilter]);

  // Coffer's own server: always on, for every agent, so Reach "On everywhere" matches it.
  const showBuiltin =
    !!builtin &&
    matchesReach(reach, { enabled: true, scope: null }) &&
    (query.trim() === "" ||
      `${builtin.name} ${builtin.url}`.toLowerCase().includes(query.trim().toLowerCase()));

  // What select-all covers: the listed servers the filters show (never the built-in one).
  const visibleUids = [...groups.values()].flat().map((i) => servers[i].uid);
  const allVisiblePicked = visibleUids.length > 0 && visibleUids.every((u) => picked.has(u));
  const toggleAll = (on: boolean) =>
    setPicked((prev) => {
      const next = new Set(prev);
      for (const u of visibleUids) {
        if (on) next.add(u);
        else next.delete(u);
      }
      return next;
    });
  const selected = servers.filter((s) => picked.has(s.uid));
  const toggle = (uid: string, on: boolean) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (on) next.add(uid);
      else next.delete(uid);
      return next;
    });
  const shown = [...groups.values()].reduce((n, g) => n + g.length, 0) + (showBuiltin ? 1 : 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-2.5 px-3 pb-2.5 pt-3.5">
        {selected.length > 0 ? (
          <McpServersBulkBar
            servers={selected}
            allChecked={allVisiblePicked}
            onToggleAll={toggleAll}
            onDone={() => setPicked(new Set())}
          />
        ) : (
          <>
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder={t("mcp.page.filter")}
              ariaLabel={t("mcp.page.filter")}
            />
            <div className="flex items-center gap-2">
              <AgentFilterPill filter={agentFilter} />
              <ReachFilter value={reach} onChange={setReach} compact />
            </div>
          </>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {error ? (
          <ListLoadError kind="mcp" error={error} onRetry={() => onRetry?.()} />
        ) : isLoading ? (
          <ListLoadingRows />
        ) : shown === 0 &&
          servers.length > 0 &&
          (query.trim() !== "" || reach !== "all" || agentFilter) ? (
          <ListNoMatch
            kind="mcp"
            query={query}
            onClear={() => {
              setQuery("");
              setReach("all");
            }}
          />
        ) : (
          GROUP_ORDER.map((group) => {
            const rows = groups.get(group) ?? [];
            if (rows.length === 0) return null;
            return (
              <section key={group} className="mb-3" aria-label={t(`mcp.page.group.${group}`)}>
                <h2 className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted">
                  {t(`mcp.page.group.${group}`)}
                  <span className="ml-auto font-book">{rows.length}</span>
                </h2>
                <ul className="flex flex-col gap-0.5">
                  {rows.map((i) => {
                    const s = servers[i];
                    return (
                      <McpServerListRow
                        key={s.uid}
                        resource={s}
                        detail={detailOf(i)}
                        tiering={splits.get(s.uid) ?? undefined}
                        agents={agents}
                        to={hrefFor(s.name)}
                        current={s.name === selectedName}
                        selecting={selected.length > 0}
                        checked={picked.has(s.uid)}
                        onCheckedChange={(on) => toggle(s.uid, on)}
                      />
                    );
                  })}
                </ul>
              </section>
            );
          })
        )}
        {isLoading || error || !showBuiltin || !builtin ? null : (
          <McpBuiltinRow server={builtin} to={hrefFor(BUILTIN_NAME)} current={builtinSelected} />
        )}
      </div>
    </div>
  );
}
