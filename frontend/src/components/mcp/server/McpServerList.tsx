// src/components/mcp/server/McpServerList.tsx — the left pane of the MCP servers page (design 4.1.01).
//
// "Filter servers" (name, title and command or URL), then the servers grouped
// by what needs the user — Needs attention (failing, launcher missing, secret
// missing, each with its reason), Not checked yet, Healthy, Off — then Built-in (Coffer's own `coffer` server, read-only). The search
// filters every row, the built-in one included. While rows are ticked the
// selection bar takes the search's place at the top; which rows are ticked
// belongs to the page, whose right pane summarises the selection. Each row
// reads its own status and tiering (both cheap, persisted reads), so the
// grouping is done here from the cached answers the rows share.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentFilterPill } from "@/components/agents/tabs/AgentFilterPill";
import { SearchInput } from "@/components/SearchInput";
import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { ListSelectAll } from "@/components/ListSelectAll";
import type { ResourceOut } from "@/lib/api/resources";
import { useAgentFilter } from "@/lib/agents/agentFilter";
import { useAgents } from "@/lib/hooks/useAgents";
import { useBuiltinMcpServer } from "@/lib/hooks/useMcpAddFlow";
import { useMcpServerListReads } from "@/lib/hooks/useMcpServerPage";
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
  /** The ticked servers' uids, and the page's setter for them. */
  picked: ReadonlySet<string>;
  onPickedChange: (picked: ReadonlySet<string>) => void;
}

export function McpServerList({
  servers,
  isLoading,
  error,
  onRetry,
  selectedName,
  hrefFor,
  builtinSelected = false,
  picked,
  onPickedChange,
}: Props) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const [query, setQuery] = useState("");
  const agentFilter = useAgentFilter();
  const { data: builtin } = useBuiltinMcpServer();

  const { details, splits } = useMcpServerListReads(servers.map((s) => s.uid));
  const detailOf = (i: number) => details.get(servers[i].uid);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out = new Map<ServerGroup, number[]>(GROUP_ORDER.map((g) => [g, []]));
    servers.forEach((s, i) => {
      const haystack = `${s.name} ${s.title ?? ""} ${transportOf(s.config).target}`.toLowerCase();
      if (q && !haystack.includes(q)) return;
      if (agentFilter && !agentFilter.matches(s)) return;
      out.get(serverState(s, detailOf(i)).group)?.push(i);
    });
    return out;
    // detailOf reads `details`, whose answers are what change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servers, query, details, agentFilter]);

  // Coffer's own server: always on, for every agent; only the search can hide it.
  const showBuiltin =
    !!builtin &&
    (query.trim() === "" ||
      `${builtin.name} ${builtin.url}`.toLowerCase().includes(query.trim().toLowerCase()));

  // The listed servers the search shows (never the built-in one): the bar's "of M".
  const visibleUids = [...groups.values()].flat().map((i) => servers[i].uid);
  const selected = servers.filter((s) => picked.has(s.uid));
  const toggle = (uid: string, on: boolean) => {
    const next = new Set(picked);
    if (on) next.add(uid);
    else next.delete(uid);
    onPickedChange(next);
  };
  const shown = [...groups.values()].reduce((n, g) => n + g.length, 0) + (showBuiltin ? 1 : 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-2.5 px-3 pb-2.5 pt-3.5">
        {selected.length > 0 ? (
          <McpServersBulkBar
            servers={selected}
            total={visibleUids.length}
            onDone={() => onPickedChange(new Set())}
          />
        ) : (
          <>
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder={t("mcp.page.filter")}
              ariaLabel={t("mcp.page.filter")}
            />
            {agentFilter ? (
              <div className="flex items-center gap-2">
                <AgentFilterPill filter={agentFilter} />
              </div>
            ) : null}
          </>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <ListSelectAll
          count={visibleUids.filter((u) => picked.has(u)).length}
          total={visibleUids.length}
          onChange={(all) => onPickedChange(all ? new Set(visibleUids) : new Set())}
        />
        {error ? (
          <ListLoadError kind="mcp" error={error} onRetry={() => onRetry?.()} />
        ) : isLoading ? (
          <ListLoadingRows />
        ) : shown === 0 && servers.length > 0 && (query.trim() !== "" || agentFilter) ? (
          <ListNoMatch kind="mcp" query={query} onClear={() => setQuery("")} />
        ) : (
          GROUP_ORDER.map((group) => {
            const rows = groups.get(group) ?? [];
            if (rows.length === 0) return null;
            return (
              <section key={group} className="mb-3" aria-label={t(`mcp.page.group.${group}`)}>
                <h2 className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted">
                  {t(`mcp.page.group.${group}`)}
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
