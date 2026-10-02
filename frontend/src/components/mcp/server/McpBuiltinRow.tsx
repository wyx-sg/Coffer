// src/components/mcp/server/McpBuiltinRow.tsx — the list's last group, Built-in, holding Coffer's own `coffer` server (board 4.1.23).
//
// The list decides whether it shows (it obeys the search, Reach and Kind
// filters, and the group hides when empty). Read-only: no checkbox (it cannot be
// selected for a bulk change) and its reach is always every connected agent.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { StatusDot } from "@/components/status/StatusDot";
import type { McpBuiltinServer } from "@/lib/api/mcpBuiltin";
import { cn } from "@/lib/utils";

interface Props {
  server: Pick<McpBuiltinServer, "name" | "tool_count">;
  to: string;
  current: boolean;
}

export function McpBuiltinRow({ server, to, current }: Props) {
  const { t } = useTranslation();
  return (
    <section className="mb-3" aria-label={t("mcp.builtin.group")}>
      <h2 className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted">
        {t("mcp.builtin.group")}
        <span className="ml-auto font-book">1</span>
      </h2>
      <ul className="flex flex-col gap-0.5">
        <li
          data-testid="mcp-builtin-row"
          className={cn(
            "flex items-center rounded-lg pl-2.5 transition-colors duration-fast",
            current ? "bg-surface-selected" : "hover:bg-surface-hover",
          )}
        >
          <Link
            to={to}
            aria-current={current ? "page" : undefined}
            className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg py-2 pr-2.5 text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring"
          >
            <StatusDot tone="ok" />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="truncate font-mono text-xs font-label">
                {server.name}{" "}
                <span className="font-sans text-2xs text-text-muted">{t("mcp.builtin.badge")}</span>
              </span>
              <span className="truncate text-xs text-text-muted">
                {t("mcp.builtin.subline", { count: server.tool_count })}
              </span>
            </span>
            <span className="shrink-0 text-xs text-text-muted">{t("agentBadge.allAgents")}</span>
          </Link>
        </li>
      </ul>
    </section>
  );
}
