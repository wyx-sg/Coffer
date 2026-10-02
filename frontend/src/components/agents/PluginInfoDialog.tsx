// src/components/agents/PluginInfoDialog.tsx — what one installed plugin is and what it provides, in a dialog.
//
// Spec agent-registry "Read one installed plugin's detail read-only". Opened
// from the plugin's name on the agent's Plugins tab. It says who made it,
// where it came from and is installed, and WHICH skills, commands, subagents,
// hook events and MCP servers it bundles — names only: the items themselves are
// not opened from here. The tab's own switch and Uninstall carry the writes.
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { Section } from "@/components/Section";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { PluginDetailOut } from "@/lib/api/agents-workspace";
import { useAgentPlugin } from "@/lib/hooks/useAgents";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] items-baseline gap-3 py-1.5">
      <dt className="text-xs text-text-subtle">{label}</dt>
      <dd className="min-w-0 break-words text-sm text-text">{children}</dd>
    </div>
  );
}

function Names({ title, names }: { title: string; names: string[] }) {
  if (names.length === 0) return null;
  return (
    <Section title={title} gap="snug">
      <div className="flex flex-wrap gap-1.5">
        {names.map((n) => (
          <Badge key={n} variant="secondary" className="font-mono">
            {n}
          </Badge>
        ))}
      </div>
    </Section>
  );
}

function Body({ detail }: { detail: PluginDetailOut }) {
  const { t } = useTranslation();
  const p = detail.plugin;
  const names = (items: { name: string }[]) => items.map((i) => i.name);
  const provides = [
    detail.skills.length,
    detail.commands.length,
    detail.agents.length,
    detail.hooks.length,
    detail.mcp_servers.length,
  ].some((n) => n > 0);
  return (
    <div className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto">
      {p.description ? <p className="text-sm text-text">{p.description}</p> : null}
      <dl className="flex flex-col divide-y divide-border-subtle border-y border-border-subtle">
        <Row label={t("agents.pluginsTab.cols.version")}>
          <span className="font-mono text-xs">{p.version ?? "—"}</span>
        </Row>
        <Row label={t("agents.pluginDetail.author")}>{p.author ?? "—"}</Row>
        {p.homepage ? (
          <Row label={t("agents.pluginDetail.homepage")}>
            <a
              href={p.homepage}
              target="_blank"
              rel="noreferrer"
              className="break-all text-accent-text underline-offset-2 hover:underline"
            >
              {p.homepage}
            </a>
          </Row>
        ) : null}
        <Row label={t("agents.pluginsTab.cols.marketplace")}>{p.marketplace}</Row>
        <Row label={t("agents.pluginDetail.installPath")}>
          {detail.install_path ? (
            <span className="flex flex-col gap-2">
              <span className="break-all font-mono text-xs">{detail.install_path}</span>
              <FileActions filePath={detail.install_path} />
            </span>
          ) : (
            <span className="text-text-muted">{t("agents.pluginDetail.notOnDisk")}</span>
          )}
        </Row>
      </dl>
      <Section title={t("agents.pluginDetail.contents")}>
        {provides ? (
          <div className="flex flex-col gap-3">
            <Names title={t("agents.pluginDetail.skills")} names={names(detail.skills)} />
            <Names title={t("agents.pluginDetail.commands")} names={names(detail.commands)} />
            <Names title={t("agents.pluginDetail.agents")} names={names(detail.agents)} />
            <Names title={t("agents.pluginDetail.hooks")} names={detail.hooks} />
            <Names title={t("agents.pluginDetail.mcpServers")} names={detail.mcp_servers} />
          </div>
        ) : (
          <p className="text-sm text-text-muted">{t("agents.pluginDetail.noContents")}</p>
        )}
      </Section>
    </div>
  );
}

interface Props {
  agentUid: string;
  /** The plugin's `<name>@<marketplace>` id; null keeps the dialog closed. */
  pluginId: string | null;
  onClose: () => void;
}

export function PluginInfoDialog({ agentUid, pluginId, onClose }: Props) {
  const { t } = useTranslation();
  const { data, isPending, error } = useAgentPlugin(agentUid, pluginId ?? "");
  return (
    <Dialog open={pluginId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{data?.plugin.name ?? pluginId?.split("@")[0]}</DialogTitle>
          <DialogDescription className="font-mono text-xs">{pluginId}</DialogDescription>
        </DialogHeader>
        {isPending ? (
          <Skeleton className="h-40 w-full" aria-busy="true" />
        ) : error || !data ? (
          <p className="text-sm text-danger" role="alert">
            {error ? translateApiError(t, error) : t("agents.pluginDetail.loadFailed")}
          </p>
        ) : (
          <Body detail={data} />
        )}
      </DialogContent>
    </Dialog>
  );
}
