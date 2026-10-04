// src/components/mcp/server/McpCapabilityTab.tsx — the open server's Resources or Prompts tab (design 4.1.11, 4.1.12).
//
// Search, "N of M on", All on · All off; each row its switch, URI or name,
// one-line description (a prompt's arguments after it) and its last-24-hours
// reads or uses; every item is loaded, 50 rows at a time ("Showing N of M",
// Show more). The gateway lists every resource and prompt as the server
// offers it, so there is no exposure setting here; the Prompts tab says above
// its toolbar where they show up.
import { useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { TruncatedText } from "@/components/ui/truncated-text";
import { Skeleton } from "@/components/ui/skeleton";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { useShowMore } from "@/lib/hooks/useShowMore";
import { capabilitiesApi } from "@/lib/hooks/useMcpCapabilityMutations";
import type { InvocationSummary } from "@/lib/hooks/useMcpServerPage";
import { ToggleSwitch } from "../CapabilityRowCells";
import { CapabilityToolbar } from "./CapabilityToolbar";
import { usageByTool } from "@/lib/mcp/serverState";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

interface Row {
  key: string;
  prefixed: string;
  description: string | null;
  enabled: boolean;
}

interface Props {
  serverUid: string;
  kind: "resource" | "prompt";
  capabilities: CapabilityListOut | undefined;
  pending: boolean;
  error: unknown;
  summary: InvocationSummary | undefined;
}

function rowsOf(t: TFunction, kind: Props["kind"], caps: CapabilityListOut | undefined): Row[] {
  if (kind === "resource")
    return (caps?.resources ?? []).map((r) => ({
      key: r.original_uri,
      prefixed: r.prefixed_uri,
      description: r.description ?? r.name,
      enabled: r.enabled,
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
  const bulk = useBulkMutate({ invalidate: [mcpCapabilitiesKey(serverUid)] });
  const rows = rowsOf(t, kind, capabilities);
  const on = rows.filter((r) => r.enabled).length;
  const usage = usageByTool(summary);
  const q = query.trim().toLowerCase();
  const shown = q ? rows.filter((r) => r.key.toLowerCase().includes(q)) : rows;
  const page = useShowMore(shown, q);
  const ns = kind === "resource" ? "resources" : "prompts";

  const setAll = (op: "enable" | "disable") =>
    void bulk.run(
      rows.filter((r) => r.enabled !== (op === "enable")),
      (r) =>
        capabilitiesApi.setEnabled(op, { serverUid, capabilityType: kind, capabilityKey: r.key }),
    );

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
            <th className="w-12 py-1.5" aria-hidden />
            <th className="py-1.5 font-semibold">{t(`mcp.page.${ns}.col`)}</th>
            <th className="py-1.5 font-semibold">{t("mcp.page.colDescription")}</th>
            <th className="w-24 py-1.5 pr-2 text-right font-semibold">{t(`mcp.page.${ns}.use`)}</th>
          </tr>
        </thead>
        <tbody>
          {page.shown.map((row) => (
            <tr key={row.key} className="h-12 border-b border-border-subtle">
              <td className="py-2 text-center">
                <ToggleSwitch serverUid={serverUid} kind={kind} row={row} />
              </td>
              <td className="py-2 pr-3">
                <TruncatedText text={row.key} mono className="text-xs font-semibold" />
              </td>
              <td className="py-2 pr-3">
                {row.description ? (
                  <TruncatedText text={row.description} className="text-xs text-text-muted" />
                ) : null}
              </td>
              <td className="py-2 pr-2 text-right tabular-nums">
                {usage.get(row.key)?.calls ?? 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );

  return (
    <div className="flex flex-col gap-3">
      {kind === "prompt" && rows.length > 0 ? (
        <p className="text-xs text-text-muted">{t("mcp.page.prompts.note")}</p>
      ) : null}
      <CapabilityToolbar
        placeholder={t(kind === "resource" ? "mcp.page.searchResources" : "mcp.page.searchPrompts")}
        query={query}
        onQueryChange={setQuery}
        on={on}
        total={rows.length}
        busy={bulk.isPending}
        onAllOn={() => setAll("enable")}
        onAllOff={() => setAll("disable")}
      />
      {body}
      {shown.length > 0 ? (
        <p className="flex items-center gap-2 px-2 text-xs text-text-muted">
          <span data-testid="mcp-caps-shown">
            {t("mcp.page.showingOf", { shown: page.shown.length, total: page.total })}
          </span>
          {page.hasMore ? (
            <Button variant="link" size="sm" onClick={page.showMore}>
              {t("mcp.page.showMore", { count: page.next })}
            </Button>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
