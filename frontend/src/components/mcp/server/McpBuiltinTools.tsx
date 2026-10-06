// src/components/mcp/server/McpBuiltinTools.tsx — the built-in `coffer` server's tools (board 4.1.23).
//
// They are always on, so there is no switch: each tool's name and what it
// does, its calls and errors in the last 24 hours, and the names agents see
// them under. On the Overview (`top`) they read "Most-called tools", busiest
// first; on the Tools tab, in the gateway's order, and a row opens, like a
// registered server's tool, to its full description, its input and the name
// agents see.
import { Fragment, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { Section } from "@/components/Section";
import type { McpBuiltinServer } from "@/lib/api/mcpBuiltin";
import { joinNames } from "@/lib/mcp/serverState";
import { cn } from "@/lib/utils";
import { paramsOf } from "./toolRows";

interface Props {
  tools: McpBuiltinServer["tools"];
  summary: McpBuiltinServer["summary"];
  /** The Overview's most-called ordering and heading. */
  top?: boolean;
}

export function McpBuiltinTools({ tools, summary, top = false }: Props) {
  const { t, i18n } = useTranslation();
  const usage = new Map(summary.by_tool.map((row) => [row.tool, row]));
  const calls = (name: string) => usage.get(name)?.calls ?? 0;
  const rows = top ? [...tools].sort((a, b) => calls(b.name) - calls(a.name)) : tools;
  const seen = tools.map((tool) => tool.qualified_name);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Section
      title={top ? t("mcp.builtin.mostCalled") : t("mcp.builtin.allTools")}
      gap="snug"
      labelled
      compact
    >
      <p className="-mt-1 text-xs text-text-muted">
        {t("mcp.builtin.alwaysOnSee", { names: joinNames(seen, i18n.language) })}
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-subtle text-left text-2xs font-semibold text-text-subtle">
            <th className="py-1.5 font-semibold">{t("mcp.builtin.colTool")}</th>
            <th className="w-24 py-1.5 text-right font-semibold">{t("mcp.builtin.colCalls")}</th>
            <th className="w-20 py-1.5 text-right font-semibold">{t("mcp.page.colErrors")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((tool) => {
            const row = usage.get(tool.name);
            const errors = row?.errors ?? 0;
            const expanded = !top && open === tool.name;
            const toggle = () => setOpen(expanded ? null : tool.name);
            return (
              <Fragment key={tool.name}>
                <tr
                  className={cn(
                    !expanded && "border-b border-border-subtle",
                    !top &&
                      "group cursor-pointer hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
                  )}
                  {...(top
                    ? {}
                    : {
                        tabIndex: 0,
                        "aria-expanded": expanded,
                        onClick: toggle,
                        onKeyDown: (e: KeyboardEvent) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggle();
                          }
                        },
                      })}
                >
                  <td className="max-w-0 py-2 pr-4">
                    <span className="flex items-center gap-1">
                      <span className="block font-mono text-sm text-text">{tool.name}</span>
                      {top ? null : (
                        <ChevronRight
                          aria-hidden
                          className={cn(
                            "size-3 shrink-0 text-text-subtle opacity-0 transition-transform group-hover:opacity-100",
                            expanded && "rotate-90 opacity-100",
                          )}
                        />
                      )}
                    </span>
                    <span className="block truncate text-xs text-text-muted">
                      {tool.description}
                    </span>
                  </td>
                  <td className="py-2 text-right tabular-nums">{row?.calls ?? 0}</td>
                  <td className={cn("py-2 text-right tabular-nums", errors > 0 && "text-danger")}>
                    {errors}
                  </td>
                </tr>
                {expanded ? (
                  <tr className="border-b border-border-subtle">
                    <td colSpan={3} className="p-0">
                      <BuiltinToolDetail tool={tool} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </Section>
  );
}

function BuiltinToolDetail({ tool }: { tool: McpBuiltinServer["tools"][number] }) {
  const { t } = useTranslation();
  const params = paramsOf(tool.input_schema);
  return (
    <div
      className="mb-2 mr-2 flex flex-col gap-2 rounded-lg bg-surface-sunken px-3 py-2.5 text-xs"
      data-testid="mcp-builtin-tool-detail"
    >
      {tool.description ? (
        <p className="whitespace-pre-line text-text">{tool.description}</p>
      ) : null}
      <div className="flex flex-col gap-1">
        <span className="font-label text-text-muted">{t("mcp.page.input")}</span>
        {params.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5" aria-label={t("mcp.page.input")}>
            {params.map((p) => (
              <li
                key={p.name}
                className="rounded-sm bg-chip px-1.5 py-0.5 font-mono text-2xs text-text"
              >
                {p.name} · {p.type}
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-text-muted">{t("mcp.capabilities.noSchema")}</span>
        )}
      </div>
      <p className="text-text-muted">
        {t("mcp.page.seenAs")} <code className="font-mono text-text">{tool.qualified_name}</code>
      </p>
    </div>
  );
}
