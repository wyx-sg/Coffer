// frontend/src/components/agents/AgentPluginDetail.tsx
// The expandable detail sub-row for the agent Plugins table: a plugin's
// manifest metadata (description / version / author / homepage) plus the
// skills, commands, and MCP servers it bundles. These are shown HERE — under
// the plugin — rather than on the agent's Skill / MCP pages, which only list
// the agent's own standalone resources. Extracted from AgentPluginsTab to keep
// that file within the component size cap.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { PluginOut } from "@/lib/api/agents";

function Bundle({ label, names }: { label: string; names: string[] | undefined }) {
  if (!names || names.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {names.map((n) => (
          <Badge key={n} variant="secondary">
            {n}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export function PluginDetailRow({ plugin: p }: { plugin: PluginOut }) {
  const { t } = useTranslation();

  const bundleCount =
    (p.skills?.length ?? 0) + (p.commands?.length ?? 0) + (p.mcp_servers?.length ?? 0);
  const hasMeta = Boolean(p.description || p.version || p.author || p.homepage);

  if (bundleCount === 0 && !hasMeta) {
    return (
      <div className="px-4 py-3 text-sm text-muted-foreground">
        {t("agents.workspace.pluginsTab.noDetail")}
      </div>
    );
  }

  return (
    <div className="space-y-3 px-4 py-3">
      {p.description ? <p className="text-sm">{p.description}</p> : null}
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        {p.version ? (
          <span>
            {t("agents.workspace.pluginsTab.version")}: {p.version}
          </span>
        ) : null}
        {p.author ? (
          <span>
            {t("agents.workspace.pluginsTab.author")}: {p.author}
          </span>
        ) : null}
        {p.homepage ? (
          <a
            href={p.homepage}
            target="_blank"
            rel="noreferrer"
            className="text-primary underline-offset-2 hover:underline"
          >
            {p.homepage}
          </a>
        ) : null}
      </div>
      {bundleCount > 0 ? (
        // Each bundle section spans the full panel width so its badges wrap
        // several per row, rather than being squeezed into a narrow column.
        <div className="space-y-3">
          <Bundle label={t("agents.workspace.pluginsTab.bundledSkills")} names={p.skills} />
          <Bundle label={t("agents.workspace.pluginsTab.bundledCommands")} names={p.commands} />
          <Bundle label={t("agents.workspace.pluginsTab.bundledMcp")} names={p.mcp_servers} />
        </div>
      ) : null}
    </div>
  );
}
