// src/components/mcp/server/McpToolDetail.tsx — one tool opened in the tool table, one column: what it does, its input, the name agents see, its last call and who made it (design 4.1.10).
import { useTranslation } from "react-i18next";

import { useAgents } from "@/lib/hooks/useAgents";
import { useMcpInvocations } from "@/lib/hooks/useMcpInvocations";
import { relativeTime } from "@/lib/mcp/serverState";
import { useExposureLabel } from "./exposureLabel";
import type { ToolRow } from "./toolRows";

interface Props {
  serverUid: string;
  row: ToolRow;
  /** Rebuilt from saved switches: the server has not said what it takes. */
  fromCache: boolean;
}

export function McpToolDetail({ serverUid, row, fromCache }: Props) {
  const { t } = useTranslation();
  const exposureLabel = useExposureLabel();
  // The summary says when a tool was last called; the newest invocation of it says by whom.
  const { data: agents = [] } = useAgents();
  const recent = useMcpInvocations({ serverUid, limit: 100, enabled: row.lastCallAt !== null });
  const last = recent.data?.invocations.find(
    (c) => c.capability_type === "tool" && c.capability_key === row.key,
  );
  const lastAgent = agents.find((a) => a.uid === last?.agent_uid)?.display_name;
  return (
    <div
      className="mb-2 ml-12 mr-2 flex flex-col gap-2 rounded-lg bg-surface-sunken px-3 py-2.5 text-xs"
      data-testid="mcp-tool-detail"
    >
      {fromCache ? (
        <p className="text-text-muted">{t("mcp.page.toolDetailCached")}</p>
      ) : (
        <>
          {row.description ? <p className="text-text">{row.description}</p> : null}
          <div className="flex flex-col gap-1">
            <span className="font-label text-text-muted">{t("mcp.page.input")}</span>
            {row.params.length > 0 ? (
              <ul className="flex flex-wrap gap-1.5" aria-label={t("mcp.page.input")}>
                {row.params.map((p) => (
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
        </>
      )}
      {row.exposure ? (
        <p className="text-text-muted" data-testid="mcp-tool-exposure-reason">
          {exposureLabel(row.exposure)} · {t(`mcp.exposure.reason.${row.exposure.reason}`)}
        </p>
      ) : null}
      <p className="text-text-muted">
        {t("mcp.page.seenAs")} <code className="font-mono text-text">{row.clientName}</code>
        {" · "}
        {t("mcp.page.characters", { count: row.clientNameLength })}
      </p>
      <p className="text-text-muted">
        {row.lastCallAt
          ? lastAgent
            ? t("mcp.page.lastCallBy", { at: relativeTime(row.lastCallAt), agent: lastAgent })
            : t("mcp.page.lastCall", { at: relativeTime(row.lastCallAt) })
          : t("mcp.page.noCallsTool")}
      </p>
    </div>
  );
}
