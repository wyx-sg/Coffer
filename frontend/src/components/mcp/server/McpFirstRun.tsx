// src/components/mcp/server/McpFirstRun.tsx — the MCP servers page with nothing registered yet (design 4.1.20; spec web-ui "Welcome an empty list with one next action").
//
// The page's whole width, no list: a welcome with a short pitch and no action of its own (the page
// header holds Add server) — no empty table, no ghost row. When the agents' own config files
// already hold MCP servers Coffer does not serve, a card lists them per agent,
// with the file each sits in (from the daemon's import plan); each row opens
// that agent's MCP servers tab, where its entries are imported.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, Server } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { useAgentDirectMcpEntries } from "@/lib/hooks/useAgentDirectMcpEntries";
import { agentTabPath } from "@/lib/agents/routes";
import { useMcpImportPlan } from "@/lib/hooks/useMcpAddFlow";
import { toEntryIn } from "../add/importPlanItems";

export function McpFirstRun() {
  const { t } = useTranslation();
  const { groups, count } = useAgentDirectMcpEntries();
  const found = groups.filter((g) => g.entries.length > 0);
  const plan = useMcpImportPlan(
    found.flatMap((g) => g.entries.map((e) => toEntryIn(g.agent.uid, e))),
    count > 0,
  );
  const fileOf = (uid: string) =>
    plan.data?.files
      .filter((f) => f.agent_uid === uid)
      .map((f) => f.display_path)
      .join(", ");

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-6 pt-24">
      <section className="flex flex-col items-center gap-2 text-center" data-testid="mcp-welcome">
        <span className="inline-flex size-10 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <Server className="size-5" strokeWidth={1.75} aria-hidden />
        </span>
        <h2 className="text-md font-semibold">{t("mcp.page.welcome.title")}</h2>
        <p className="max-w-sm text-sm text-text-muted">{t("mcp.page.welcome.body")}</p>
      </section>
      {count > 0 ? (
        <section
          className="flex w-full flex-col gap-3 rounded-xl border border-border-subtle p-5"
          data-testid="mcp-welcome-found"
        >
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold">{t("mcp.page.welcome.foundTitle", { count })}</h3>
            <p className="text-xs text-text-muted">{t("mcp.page.welcome.foundBody")}</p>
          </div>
          <ul className="flex flex-col">
            {found.map((g) => (
              <li key={g.agent.uid} className="border-t border-border-subtle">
                <Link
                  to={agentTabPath(g.agent.type, "mcp-servers")}
                  className="flex items-center gap-3 rounded-sm py-3 text-sm transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                >
                  <AgentBadge type={g.agent.type} name={g.agent.display_name} size="md" />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="font-label text-text">{g.agent.display_name}</span>
                    <span className="truncate font-mono text-xs text-text-muted">
                      {fileOf(g.agent.uid) || " "}
                    </span>
                  </span>
                  <span className="flex flex-wrap justify-end gap-1.5">
                    {g.entries.map((e) => (
                      <code
                        key={e.name}
                        className="rounded-sm border border-border-subtle bg-surface-sunken px-1.5 py-0.5 text-xs"
                      >
                        {e.name}
                      </code>
                    ))}
                  </span>
                  <ChevronRight aria-hidden className="size-4 shrink-0 text-text-muted" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
