// src/components/custom-tools/GroupTopTools.tsx — a group Overview's "Most-called tools": the busiest four by 24-hour
// calls, read-only (the switches and exposure are on the Tools tab), with "Show all N in Tools" — the MCP server
// Overview's table (TopToolsTable), Listed / Behind search column included while tiering hides any tool.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import { TopToolsTable } from "@/components/mcp/server/TopToolsTable";
import { busiestFirst, type ToolRow } from "@/components/mcp/server/toolRows";

const SHOWN = 4;

interface Props {
  name: string;
  rows: readonly ToolRow[];
  toolsHref: string;
}

export function GroupTopTools({ name, rows, toolsHref }: Props) {
  const { t } = useTranslation();
  return (
    <Section title={t("mcp.page.mostCalled")} gap="snug" labelled compact>
      <p className="-mt-1 text-xs text-text-muted">{t("mcp.page.mostCalledSub", { name })}</p>
      {rows.length === 0 ? (
        <p className="py-2 text-xs text-text-muted">{t("customTools.tools.empty")}</p>
      ) : (
        <>
          <TopToolsTable
            rows={busiestFirst(rows).slice(0, SHOWN)}
            showListing={rows.some((r) => r.listing !== null)}
            label={t("mcp.page.mostCalled")}
          />
          {rows.length > SHOWN ? (
            <Link
              to={toolsHref}
              className="pt-1 text-xs font-label text-accent-text hover:underline"
            >
              {t("mcp.page.showAllInTools", { count: rows.length })}
            </Link>
          ) : null}
        </>
      )}
    </Section>
  );
}
