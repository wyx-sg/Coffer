// frontend/src/components/agents/AgentMcpEntryOverview.tsx
// The body of a direct MCP server's detail page (spec agent-registry "Show one
// direct MCP entry's full configuration without its secrets"): everything the
// agent's own config file says about the entry, read-only, in the same card
// and definition-list shape as the managed server's Overview tab.
//
// No value here can be a secret. The daemon sends env and header KEY NAMES
// only, and withholds the value of any other secret-looking key (`masked`), so
// this component has nothing to hide — it only says which names are set and
// which of them look secret.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { McpEntryDetailOut } from "@/lib/api/agents-workspace";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </>
  );
}

/** Key names with a "set" / "secret · hidden" marker — never a value. */
function KeyList({ keys, secret }: { keys: string[]; secret: Set<string> }) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-1">
      {keys.map((k) => (
        <li key={k} className="flex flex-wrap items-center gap-2">
          <span className="break-all font-mono text-xs">{k}</span>
          <Badge variant={secret.has(k) ? "secondary" : "outline"}>
            {secret.has(k)
              ? t("agents.workspace.mcp.detail.secret")
              : t("agents.workspace.mcp.detail.set")}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

export function AgentMcpEntryOverview({ entry }: { entry: McpEntryDetailOut }) {
  const { t } = useTranslation();
  const secret = new Set(entry.secret_keys);
  const mono = "break-all font-mono text-xs";

  return (
    <div className="space-y-4">
      <Card className="paper-card">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">{t("mcp.server.overview.config")}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 text-sm sm:grid-cols-[minmax(8rem,auto)_1fr]">
            <Row label={t("mcp.server.overview.transport")}>
              <span className="font-mono">{entry.transport}</span>
            </Row>
            {entry.transport === "stdio" ? (
              <>
                <Row label={t("mcp.server.overview.command")}>
                  <span className={mono}>{entry.command ?? "—"}</span>
                </Row>
                {entry.args.length > 0 ? (
                  <Row label={t("agents.workspace.mcp.detail.args")}>
                    <ol className="space-y-0.5">
                      {entry.args.map((a, i) => (
                        <li key={i} className={mono}>
                          {a}
                        </li>
                      ))}
                    </ol>
                  </Row>
                ) : null}
              </>
            ) : (
              <Row label={t("mcp.server.overview.url")}>
                <span className={mono}>{entry.url ?? "—"}</span>
              </Row>
            )}
            {entry.cwd ? (
              <Row label={t("agents.workspace.mcp.detail.cwd")}>
                <span className={mono}>{entry.cwd}</span>
              </Row>
            ) : null}
            {entry.enabled !== null ? (
              <Row label={t("agents.workspace.mcp.detail.enabled")}>
                {entry.enabled
                  ? t("agents.workspace.mcp.detail.yes")
                  : t("agents.workspace.mcp.detail.no")}
              </Row>
            ) : null}
            {entry.env_keys.length > 0 ? (
              <Row label={t("agents.workspace.mcp.detail.env")}>
                <KeyList keys={entry.env_keys} secret={secret} />
              </Row>
            ) : null}
            {entry.header_keys.length > 0 ? (
              <Row label={t("agents.workspace.mcp.detail.headers")}>
                <KeyList keys={entry.header_keys} secret={secret} />
              </Row>
            ) : null}
            {entry.extra.length > 0 ? (
              <Row label={t("agents.workspace.mcp.detail.other")}>
                <ul className="space-y-1">
                  {entry.extra.map((f) => (
                    <li key={f.key} className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs">{f.key}</span>
                      {f.masked ? (
                        <Badge variant="secondary">{t("agents.workspace.mcp.detail.hidden")}</Badge>
                      ) : (
                        <span className={`${mono} text-muted-foreground`}>{f.value}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </Row>
            ) : null}
          </dl>
        </CardContent>
      </Card>

      <Card className="paper-card">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">
            {t("agents.workspace.mcp.detail.file")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <dl className="grid gap-3 text-sm sm:grid-cols-[minmax(8rem,auto)_1fr]">
            <Row label={t("agents.workspace.mcp.detail.source")}>
              <Badge variant="outline">{entry.source}</Badge>
            </Row>
            <Row label={t("agents.workspace.mcp.detail.file")}>
              <span className={mono}>{entry.path}</span>
            </Row>
          </dl>
          <FileActions filePath={entry.path} />
        </CardContent>
      </Card>
    </div>
  );
}
