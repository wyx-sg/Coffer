// src/components/mcp/server/McpCapabilityTab.tsx — the open server's Resources or Prompts tab (design 4.1.11, 4.1.12).
//
// Search; each row its select box, its switch, URI or name,
// one-line description (a prompt's arguments after it) and its last-24-hours
// reads or uses; a row opens, like a tool's, to its details (McpCapabilityRow);
// every item is loaded and rendered whole (100 at a time as
// the end scrolls into view, past 100). The header box ticks every item the
// search matches; ticked items swap the toolbar for the selection bar (Turn
// on, Turn off). The gateway lists every resource and prompt as the server
// offers it, so there is no exposure setting here; the Prompts tab says above
// its toolbar where they show up.
import { useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { ListSelectionBar } from "@/components/ListSelectionBar";
import { useTableSelection } from "@/components/DataTableSelection";
import { BulkOnOffActions } from "@/components/BulkOnOffActions";
import { LoadMoreSentinel } from "@/components/ui/load-more";
import { Skeleton } from "@/components/ui/skeleton";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { useGrowingList } from "@/lib/hooks/useGrowingList";
import { capabilitiesApi } from "@/lib/hooks/useMcpCapabilityMutations";
import type { InvocationSummary } from "@/lib/hooks/useMcpServerPage";
import { CapabilityToolbar, SelectAllBox } from "./CapabilityToolbar";
import { McpCapabilityRow } from "./McpCapabilityRow";
import { usageByTool } from "@/lib/mcp/serverState";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

export interface CapabilityRow {
  key: string;
  prefixed: string;
  description: string | null;
  enabled: boolean;
  resource?: components["schemas"]["MCPResourceView"];
  prompt?: components["schemas"]["MCPPromptView"];
}

type Row = CapabilityRow;

interface Props {
  serverUid: string;
  kind: "resource" | "prompt";
  capabilities: CapabilityListOut | undefined;
  pending: boolean;
  error: unknown;
  summary: InvocationSummary | undefined;
}

const rowKey = (row: Row) => row.key;

function rowsOf(t: TFunction, kind: Props["kind"], caps: CapabilityListOut | undefined): Row[] {
  if (kind === "resource")
    return (caps?.resources ?? []).map((r) => ({
      key: r.original_uri,
      prefixed: r.prefixed_uri,
      description: r.description ?? r.name ?? null,
      enabled: r.enabled,
      resource: r,
    }));
  return (caps?.prompts ?? []).map((p) => {
    const args = p.arguments.map((a) => a.name).join(", ");
    const parts = [
      p.description,
      args ? t("mcp.page.prompts.arguments", { names: args }) : null,
    ].filter(Boolean);
    return {
      key: p.original_name,
      prefixed: p.prefixed_name,
      description: parts.length > 0 ? parts.join(" · ") : null,
      enabled: p.enabled,
      prompt: p,
    };
  });
}

export function McpCapabilityTab({
  serverUid,
  kind,
  capabilities,
  pending,
  error,
  summary,
}: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const bulk = useBulkMutate({ invalidate: [mcpCapabilitiesKey(serverUid)] });
  const rows = rowsOf(t, kind, capabilities);
  const usage = usageByTool(summary);
  const q = query.trim().toLowerCase();
  const shown = q ? rows.filter((r) => r.key.toLowerCase().includes(q)) : rows;
  const page = useGrowingList(shown, q);
  const ns = kind === "resource" ? "resources" : "prompts";

  const sel = useTableSelection(shown, rowKey);
  const selected = sel.selectedRows;
  const selection = {
    keys: sel.keys,
    toggle: sel.toggle,
    allKeys: shown.map(rowKey),
    setMany: sel.setMany,
    count: selected.length,
  };

  const setSelected = async (op: "enable" | "disable") => {
    await bulk.run(
      selected.filter((r) => r.enabled !== (op === "enable")),
      (r) =>
        capabilitiesApi.setEnabled(op, { serverUid, capabilityType: kind, capabilityKey: r.key }),
    );
    sel.clear();
  };

  let body: JSX.Element;
  if (pending) body = <Skeleton className="h-32 w-full" />;
  else if (rows.length === 0)
    body = (
      <p className="py-2 text-xs text-text-muted">
        {error
          ? t("mcp.capabilities.loadError")
          : t(
              kind === "resource"
                ? "mcp.capabilities.emptyResource"
                : "mcp.capabilities.emptyPrompt",
            )}
      </p>
    );
  else if (shown.length === 0)
    body = <p className="py-2 text-xs text-text-muted">{t("mcp.capabilities.noMatches")}</p>;
  else
    body = (
      <table className="w-full table-fixed text-sm" aria-label={t(`mcp.server.tabs.${ns}`)}>
        <thead>
          <tr className="border-b border-border-subtle text-left text-2xs font-semibold text-text-muted">
            <th className="w-10 py-1.5 pl-2">
              <SelectAllBox selection={selection} />
            </th>
            <th className="w-12 py-1.5" aria-hidden />
            <th className="py-1.5 font-semibold">{t(`mcp.page.${ns}.col`)}</th>
            <th className="py-1.5 font-semibold">{t("mcp.page.colDescription")}</th>
            <th className="w-24 py-1.5 pr-2 text-right font-semibold">{t(`mcp.page.${ns}.use`)}</th>
          </tr>
        </thead>
        <tbody>
          {page.shown.map((row) => (
            <McpCapabilityRow
              key={row.key}
              serverUid={serverUid}
              kind={kind}
              row={row}
              uses={usage.get(row.key)?.calls ?? 0}
              selection={selection}
              expanded={open === row.key}
              onToggle={() => setOpen(open === row.key ? null : row.key)}
            />
          ))}
        </tbody>
      </table>
    );

  return (
    <div className="flex flex-col gap-3">
      {kind === "prompt" && rows.length > 0 ? (
        <p className="text-xs text-text-muted">{t("mcp.page.prompts.note")}</p>
      ) : null}
      {selected.length > 0 ? (
        <ListSelectionBar
          label={t(kind === "resource" ? "mcp.page.bulkResources" : "mcp.page.bulkPrompts")}
          count={selected.length}
          total={shown.length}
          onClear={sel.clear}
        >
          <BulkOnOffActions
            busy={bulk.isPending}
            offCount={selected.filter((r) => !r.enabled).length}
            onCount={selected.filter((r) => r.enabled).length}
            onTurnOn={() => void setSelected("enable")}
            onTurnOff={() => void setSelected("disable")}
          />
        </ListSelectionBar>
      ) : (
        <CapabilityToolbar
          placeholder={t(
            kind === "resource" ? "mcp.page.searchResources" : "mcp.page.searchPrompts",
          )}
          query={query}
          onQueryChange={setQuery}
        />
      )}
      {body}
      <LoadMoreSentinel active={page.hasMore} onVisible={page.more} version={page.shown.length} />
    </div>
  );
}
