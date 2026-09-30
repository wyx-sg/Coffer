// src/components/mcp/server/McpBuiltinTools.tsx — the built-in `coffer` server's tools (board 4.1.23).
//
// They are always on, so there is no switch: each tool's name and what it
// does, its calls and errors in the last 24 hours, and the names agents see
// them under. On the Overview (`top`) they read "Most-called tools", busiest
// first; on the Tools tab, in the gateway's order.
import { useTranslation } from "react-i18next";

import type { McpBuiltinServer } from "@/lib/api/mcpBuiltin";
import { cn } from "@/lib/utils";

interface Props {
  tools: McpBuiltinServer["tools"];
  summary: McpBuiltinServer["summary"];
  /** The Overview's most-called ordering and heading. */
  top?: boolean;
}

export function McpBuiltinTools({ tools, summary, top = false }: Props) {
  const { t } = useTranslation();
  const usage = new Map(summary.by_tool.map((row) => [row.tool, row]));
  const calls = (name: string) => usage.get(name)?.calls ?? 0;
  const rows = top ? [...tools].sort((a, b) => calls(b.name) - calls(a.name)) : tools;
  const seen = tools.map((tool) => tool.qualified_name);
  return (
    <section className="flex flex-col gap-2" aria-labelledby="mcp-builtin-tools">
      <h3 id="mcp-builtin-tools" className="flex items-baseline gap-2 text-sm font-semibold">
        {top ? t("mcp.builtin.mostCalled") : t("mcp.builtin.allTools")}
        <span className="text-xs font-book text-text-muted">
          {t("mcp.builtin.alwaysOn", { count: tools.length })}
        </span>
      </h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-subtle text-left text-2xs font-semibold text-text-muted">
            <th className="py-1.5 font-semibold">{t("mcp.builtin.colTool")}</th>
            <th className="w-24 py-1.5 text-right font-semibold">{t("mcp.builtin.colCalls")}</th>
            <th className="w-20 py-1.5 text-right font-semibold">{t("mcp.page.colErrors")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((tool) => {
            const row = usage.get(tool.name);
            const errors = row?.errors ?? 0;
            return (
              <tr key={tool.name} className="border-b border-border-subtle">
                <td className="max-w-0 py-2 pr-4">
                  <span className="block font-mono text-sm text-text">{tool.name}</span>
                  <span className="block truncate text-xs text-text-muted">{tool.description}</span>
                </td>
                <td className="py-2 text-right tabular-nums">{row?.calls ?? 0}</td>
                <td className={cn("py-2 text-right tabular-nums", errors > 0 && "text-danger")}>
                  {errors}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-xs text-text-muted">
        {t("mcp.builtin.seenAs", {
          names: seen.slice(0, -1).join(", "),
          last: seen[seen.length - 1] ?? "",
          count: seen.length,
        })}
      </p>
    </section>
  );
}
