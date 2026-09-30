// src/components/mcp/server/McpFirstRun.tsx — the MCP servers page with nothing registered yet (design 4.1.20; spec web-ui "Welcome an empty list with one next action").
//
// A welcome card with a short pitch and one primary action, Add server — no
// empty table, no ghost row. When the agents' own config files already hold
// MCP servers Coffer does not serve, a second card lists them per agent and
// offers Review and import.
import { useTranslation } from "react-i18next";
import { Plus, Server } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Button } from "@/components/ui/button";
import { useAgentDirectMcpEntries } from "@/lib/hooks/useAgentDirectMcpEntries";

interface Props {
  onAdd: () => void;
  onImport: () => void;
}

export function McpFirstRun({ onAdd, onImport }: Props) {
  const { t } = useTranslation();
  const { groups, count } = useAgentDirectMcpEntries();
  const found = groups.filter((g) => g.entries.length > 0);

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <section
        className="flex flex-col items-start gap-3 rounded-xl border border-border-subtle bg-surface-raised p-6"
        data-testid="mcp-welcome"
      >
        <span className="inline-flex size-9 items-center justify-center rounded-lg bg-surface-sunken text-text-muted">
          <Server className="size-5" strokeWidth={1.75} aria-hidden />
        </span>
        <h2 className="text-md font-bold">{t("mcp.page.welcome.title")}</h2>
        <p className="max-w-prose text-sm text-text-muted">{t("mcp.page.welcome.body")}</p>
        <Button onClick={onAdd}>
          <Plus aria-hidden /> {t("resources.addServer")}
        </Button>
      </section>
      {count > 0 ? (
        <section
          className="flex flex-col gap-3 rounded-xl border border-border-subtle p-5"
          data-testid="mcp-welcome-found"
        >
          <h3 className="text-sm font-semibold">{t("mcp.page.welcome.foundTitle", { count })}</h3>
          <p className="text-xs text-text-muted">{t("mcp.page.welcome.foundBody")}</p>
          <ul className="flex flex-col gap-2">
            {found.map((g) => (
              <li key={g.agent.uid} className="flex flex-wrap items-center gap-3 text-sm">
                <AgentBadge type={g.agent.type} name={g.agent.display_name} showName size="sm" />
                <span className="font-mono text-xs text-text-muted">{g.entries[0]?.source}</span>
                <span className="flex flex-wrap gap-1.5">
                  {g.entries.map((e) => (
                    <code
                      key={e.name}
                      className="rounded-sm bg-surface-sunken px-1.5 py-0.5 text-xs"
                    >
                      {e.name}
                    </code>
                  ))}
                </span>
              </li>
            ))}
          </ul>
          <div>
            <Button variant="outline" onClick={onImport}>
              {t("mcp.page.welcome.reviewImport")}
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
