// src/components/mcp/server/McpServerList.tsx — the left pane of the MCP servers page (design 4.1.01).
//
// "Filter servers" (name, title and command or URL), then the servers grouped
// by what needs the user — Needs attention (failing, launcher missing, secret
// missing, each with its reason), Healthy, Not checked yet, Off — with a count
// each, and the selection bar while rows are ticked. Each row reads its own
// status and tiering (both cheap, persisted reads), so the grouping is done
// here from the cached answers the rows share.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Skeleton } from "@/components/ui/skeleton";
import type { ResourceOut } from "@/lib/api/resources";
import { useAgents } from "@/lib/hooks/useAgents";
import { useMcpServerListReads } from "@/lib/hooks/useMcpServerPage";
import { McpServerListRow } from "./McpServerListRow";
import { McpServersBulkBar } from "./McpServersBulkBar";
import { GROUP_ORDER, serverState, transportOf, type ServerGroup } from "./serverState";

interface Props {
  servers: ResourceOut[];
  isLoading: boolean;
  selectedName: string | null;
  hrefFor: (name: string) => string;
}

export function McpServerList({ servers, isLoading, selectedName, hrefFor }: Props) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());

  const { details, splits } = useMcpServerListReads(servers.map((s) => s.uid));
  const detailOf = (i: number) => details.get(servers[i].uid);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out = new Map<ServerGroup, number[]>(GROUP_ORDER.map((g) => [g, []]));
    servers.forEach((s, i) => {
      const haystack = `${s.name} ${s.title ?? ""} ${transportOf(s.config).target}`.toLowerCase();
      if (q && !haystack.includes(q)) return;
      out.get(serverState(s, detailOf(i)).group)?.push(i);
    });
    return out;
    // detailOf reads `details`, whose answers are what change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servers, query, details]);

  const selected = servers.filter((s) => picked.has(s.uid));
  const toggle = (uid: string, on: boolean) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (on) next.add(uid);
      else next.delete(uid);
      return next;
    });
  const shown = [...groups.values()].reduce((n, g) => n + g.length, 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="px-3 pb-2.5 pt-3.5">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t("mcp.page.filter")}
          ariaLabel={t("mcp.page.filter")}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {isLoading ? (
          <div className="space-y-2 px-2.5 py-1" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : shown === 0 && servers.length > 0 ? (
          <p className="px-2.5 py-3 text-xs text-text-muted">{t("mcp.page.noMatches")}</p>
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
      </div>
      {selected.length > 0 ? (
        <McpServersBulkBar servers={selected} onDone={() => setPicked(new Set())} />
      ) : null}
    </div>
  );
}
