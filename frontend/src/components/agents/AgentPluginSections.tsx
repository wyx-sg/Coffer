// src/components/agents/AgentPluginSections.tsx — spec agent-registry
// "Read one installed plugin's detail read-only".
// The two cards of the plugin detail page (pages/AgentPluginPage): Overview —
// the manifest metadata, where the plugin came from and where it is installed —
// and Contents — every skill, command, subagent, hook event and MCP server the
// plugin's package contributes. These components belong to the plugin, so they
// are shown here rather than on the agent's Skills / MCP tabs, which list only
// the agent's own standalone resources. Extracted to keep the page under its
// size cap.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PluginComponentOut, PluginDetailOut } from "@/lib/api/agents-workspace";

export function PluginOverviewCard({ detail }: { detail: PluginDetailOut }) {
  const { t } = useTranslation();
  const p = detail.plugin;
  return (
    <Card>
      <CardContent className="space-y-4 py-6">
        {p.description ? (
          <p className="max-w-prose text-sm text-muted-foreground">{p.description}</p>
        ) : null}
        <dl className="grid gap-y-3 text-sm sm:grid-cols-[12rem_1fr]">
          <dt className="text-muted-foreground">{t("agents.pluginsTab.cols.version")}</dt>
          <dd className="font-mono text-xs">{p.version ?? "—"}</dd>

          <dt className="text-muted-foreground">{t("agents.pluginDetail.author")}</dt>
          <dd>{p.author ?? "—"}</dd>

          <dt className="text-muted-foreground">{t("agents.pluginDetail.homepage")}</dt>
          <dd className="break-all">
            {p.homepage ? (
              <a
                href={p.homepage}
                target="_blank"
                rel="noreferrer"
                className="text-primary underline-offset-2 hover:underline"
              >
                {p.homepage}
              </a>
            ) : (
              "—"
            )}
          </dd>

          <dt className="text-muted-foreground">{t("agents.pluginsTab.cols.marketplace")}</dt>
          <dd>
            {p.marketplace}
            {detail.marketplace_source ? (
              <span className="ml-2 font-mono text-xs text-muted-foreground">
                ({detail.marketplace_source})
              </span>
            ) : null}
          </dd>

          <dt className="text-muted-foreground">{t("agents.pluginDetail.installPath")}</dt>
          <dd className="space-y-2">
            {detail.install_path ? (
              <>
                <span className="block break-all font-mono text-xs">{detail.install_path}</span>
                <FileActions filePath={detail.install_path} />
              </>
            ) : (
              <span className="text-muted-foreground">{t("agents.pluginDetail.notOnDisk")}</span>
            )}
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

function ComponentList({ label, items }: { label: string; items: PluginComponentOut[] }) {
  if (items.length === 0) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">
        {label} <span className="text-muted-foreground">({items.length})</span>
      </h3>
      <ul className="divide-y rounded-md border">
        {items.map((c) => (
          <li key={c.name} className="px-3 py-2">
            <span className="font-mono text-xs">{c.name}</span>
            {c.description ? (
              <p className="mt-0.5 text-sm text-muted-foreground">{c.description}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function NameList({ label, names }: { label: string; names: string[] }) {
  if (names.length === 0) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">
        {label} <span className="text-muted-foreground">({names.length})</span>
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {names.map((n) => (
          <Badge key={n} variant="secondary" className="font-mono">
            {n}
          </Badge>
        ))}
      </div>
    </section>
  );
}

export function PluginContentsCard({ detail }: { detail: PluginDetailOut }) {
  const { t } = useTranslation();
  const empty =
    detail.skills.length +
      detail.commands.length +
      detail.agents.length +
      detail.hooks.length +
      detail.mcp_servers.length ===
    0;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("agents.pluginDetail.contents")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {empty ? (
          <p className="text-sm text-muted-foreground">{t("agents.pluginDetail.noContents")}</p>
        ) : (
          <>
            <ComponentList label={t("agents.pluginDetail.skills")} items={detail.skills} />
            <ComponentList label={t("agents.pluginDetail.commands")} items={detail.commands} />
            <ComponentList label={t("agents.pluginDetail.agents")} items={detail.agents} />
            <NameList label={t("agents.pluginDetail.hooks")} names={detail.hooks} />
            <NameList label={t("agents.pluginDetail.mcpServers")} names={detail.mcp_servers} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
