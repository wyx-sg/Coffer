// src/components/mcp/server/McpToolDetail.tsx — one tool opened in the tool table: what it does, its input, the name agents see, its last call (design 4.1.02).
import { useTranslation } from "react-i18next";

import { relativeTime } from "./serverState";
import type { ToolRow } from "./toolRows";

interface Props {
  row: ToolRow;
  /** Rebuilt from saved switches: the server has not said what it takes. */
  fromCache: boolean;
}

export function McpToolDetail({ row, fromCache }: Props) {
  const { t } = useTranslation();
  return (
    <div
      className="mb-2 ml-12 mr-2 flex flex-wrap gap-x-6 gap-y-3 rounded-lg bg-surface-sunken px-3 py-2.5 text-xs"
      data-testid="mcp-tool-detail"
    >
      <div className="flex min-w-0 flex-1 basis-80 flex-col gap-2">
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
        <p className="text-text-muted">
          {t("mcp.page.seenAs")} <code className="font-mono text-text">{row.clientName}</code>
          {" · "}
          {t("mcp.page.characters", { count: row.clientNameLength })}
        </p>
      </div>
      <div className="flex shrink-0 flex-col gap-1 text-text-muted">
        {row.calls !== null ? (
          <span>{t("mcp.page.toolUse", { calls: row.calls, errors: row.errors ?? 0 })}</span>
        ) : null}
        {row.lastCallAt ? (
          <span>{t("mcp.page.lastCall", { at: relativeTime(row.lastCallAt) })}</span>
        ) : row.calls === null ? (
          <span>{t("mcp.page.noCallsTool")}</span>
        ) : null}
      </div>
    </div>
  );
}
