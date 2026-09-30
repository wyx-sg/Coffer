// src/components/mcp/server/McpSecretFacts.tsx — a server whose secret is missing: which setting cites which secret, and its last success (design 4.1.05).
import { useTranslation } from "react-i18next";

import { StatusPill } from "@/components/status/StatusPill";
import type { ResourceOut } from "@/lib/api/resources";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import { formatDateTime } from "@/lib/utils";
import { secretLabel, transportOf } from "./serverState";

interface Props {
  resource: ResourceOut;
  detail: McpStatusDetail | null | undefined;
}

export function McpSecretFacts({ resource, detail }: Props) {
  const { t } = useTranslation();
  const refs =
    (resource.config as { transport?: { secret_refs?: Record<string, string> } } | null)
      ?.transport?.secret_refs ?? {};
  const http = transportOf(resource.config).type === "http";
  const missingRef = detail?.missing_secret_ref ?? null;
  const entries = Object.entries(refs);
  if (entries.length === 0) return null;

  return (
    <section className="flex flex-col gap-1" aria-labelledby="mcp-secrets">
      <h3 id="mcp-secrets" className="text-sm font-semibold text-text">
        {t("mcp.page.secrets.title")}
      </h3>
      <dl className="flex flex-col">
        {entries.map(([key, ref]) => (
          <div key={key} className="flex gap-3 border-b border-border-subtle py-2.5 text-sm">
            <dt className="w-36 shrink-0 text-xs text-text-muted">
              {http ? t("mcp.page.secrets.header") : t("mcp.page.secrets.env")}
            </dt>
            <dd className="min-w-0 font-mono text-xs text-text">
              {key} → {`{${secretLabel(ref)}}`}
            </dd>
          </div>
        ))}
        {entries.map(([key, ref]) => (
          <div key={`s-${key}`} className="flex gap-3 border-b border-border-subtle py-2.5 text-sm">
            <dt className="w-36 shrink-0 text-xs text-text-muted">
              {t("mcp.page.secrets.secret")}
            </dt>
            <dd className="flex min-w-0 items-center gap-2">
              <span className="font-mono text-xs text-text">{secretLabel(ref)}</span>
              {ref === missingRef ? (
                <StatusPill tone="err">{t("mcp.page.secrets.missing")}</StatusPill>
              ) : (
                <StatusPill tone="ok">{t("mcp.page.secrets.stored")}</StatusPill>
              )}
            </dd>
          </div>
        ))}
        <div className="flex gap-3 py-2.5 text-sm">
          <dt className="w-36 shrink-0 text-xs text-text-muted">
            {t("mcp.page.secrets.lastSuccess")}
          </dt>
          <dd className="min-w-0 text-text">
            {detail?.last_ok_at ? formatDateTime(detail.last_ok_at) : t("mcp.page.secrets.never")}
          </dd>
        </div>
      </dl>
    </section>
  );
}
