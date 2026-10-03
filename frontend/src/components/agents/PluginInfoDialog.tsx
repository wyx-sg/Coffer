// src/components/agents/PluginInfoDialog.tsx — what one installed plugin is and what it provides, in a dialog (board 2.1.60, 640).
//
// Spec agent-registry "Read one installed plugin's detail read-only". Opened
// from the plugin's name on the agent's Plugins tab. It says what the plugin is
// (description, then version · marketplace · where it is installed) and WHICH
// skills, commands, subagents, hook events and MCP servers it bundles, each
// section a title with its count over hairline rows (name, then what it does).
// The items themselves are not opened from here; the tab's own switch and ⋯
// carry the writes.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import type { PluginDetailOut } from "@/lib/api/agents-workspace";
import { useAgentPlugin } from "@/lib/hooks/useAgents";

interface Item {
  name: string;
  description?: string | null;
}

function Group({ title, items }: { title: string; items: Item[] }) {
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col">
      <h3 className="flex items-baseline gap-1.5 pb-1.5 text-sm font-semibold text-text">
        {title}
        <span className="text-xs font-normal text-text-subtle">{items.length}</span>
      </h3>
      <ul className="border-t border-border-subtle">
        {items.map((item) => (
          <li
            key={item.name}
            className="grid grid-cols-[minmax(0,200px)_minmax(0,1fr)] items-baseline gap-4 border-b border-border-subtle py-2"
          >
            <span className="break-all font-mono text-xs text-text">{item.name}</span>
            <span className="text-xs text-text-muted">{item.description}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Body({ detail }: { detail: PluginDetailOut }) {
  const { t } = useTranslation();
  const named = (names: string[]): Item[] => names.map((name) => ({ name }));
  const provides = [
    detail.skills,
    detail.commands,
    detail.agents,
    detail.hooks,
    detail.mcp_servers,
  ].some((list) => list.length > 0);
  return (
    <div className="flex max-h-[60vh] flex-col gap-5 overflow-y-auto pr-1">
      {provides ? (
        <>
          <Group title={t("agents.pluginDetail.skills")} items={detail.skills} />
          <Group title={t("agents.pluginDetail.commands")} items={detail.commands} />
          <Group title={t("agents.pluginDetail.agents")} items={detail.agents} />
          <Group title={t("agents.pluginDetail.hooks")} items={named(detail.hooks)} />
          <Group title={t("agents.pluginDetail.mcpServers")} items={named(detail.mcp_servers)} />
        </>
      ) : (
        <p className="text-sm text-text-muted">{t("agents.pluginDetail.noContents")}</p>
      )}
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
  const p = data?.plugin;
  return (
    <Dialog open={pluginId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-[640px]">
        <DialogHeader>
          <DialogTitle className="font-mono">{p?.name ?? pluginId?.split("@")[0]}</DialogTitle>
          {p?.description ? <DialogDescription>{p.description}</DialogDescription> : null}
          {p ? (
            <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-text-muted">
              <span className="font-mono">{p.version ?? t("common.emptyValue")}</span>
              <span aria-hidden className="text-text-subtle">
                ·
              </span>
              <span>{p.marketplace}</span>
              {data?.install_path ? (
                <>
                  <span aria-hidden className="text-text-subtle">
                    ·
                  </span>
                  <span className="break-all font-mono">
                    {abbreviateHomePath(data.install_path)}
                  </span>
                </>
              ) : (
                <>
                  <span aria-hidden className="text-text-subtle">
                    ·
                  </span>
                  <span>{t("agents.pluginDetail.notOnDisk")}</span>
                </>
              )}
            </p>
          ) : null}
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
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
