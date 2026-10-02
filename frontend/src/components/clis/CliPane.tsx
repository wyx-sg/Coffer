// src/components/clis/CliPane.tsx — the CLIs page's detail pane: one command-line tool.
//
// Spec web-ui "Show every CLI a skill requires on the CLIs page". The header
// names the command with its status pill (and an Added tag for a tool added by
// hand) and "<title> · needed by N skills" — or "… · added by you" when no skill
// or MCP server needs it — and, for a command that needs the person (missing,
// too old, not logged in), its one remedy: the daemon's hand-off prompt
// (AgentHandoff). A tool added by hand carries Edit and Remove. Then the
// problem banner and two tabs, in the path: Overview (Command / Login /
// Needed by) and Commands (the tool's whole interface, read from its help). A
// command not in the list (a deep link the list has not caught up with) is
// read on its own.
import { SquareTerminal } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { PageFallback } from "@/components/PageFallback";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { StatusPill } from "@/components/status/StatusPill";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { cliTone, neededByCount } from "@/lib/clis/format";
import { CLI_TABS, DEFAULT_CLI_TAB } from "@/lib/clis/tabs";
import { useDetailTab } from "@/lib/detailTabs";
import { useCli, useCliInterfaceAuto } from "@/lib/hooks/useClis";
import { CliActions } from "./CliActions";
import { CliCommandsTab } from "./CliCommandsTab";
import { CliDetailSections } from "./CliDetailSections";
import { CliProblemBanner } from "./CliProblemBanner";

interface Props {
  command: string;
  /** The command's row from the list, when the list has it. */
  listed: Cli | undefined;
  /** A tool added by hand was removed and nothing else requires it. */
  onRemoved: () => void;
}

function Subtitle({ cli }: { cli: Cli }) {
  const { t } = useTranslation();
  const title = cli.title ?? cli.command;
  const needed = cli.needed_by.length + cli.needed_by_servers.length;
  let text: string;
  if (needed === 0) text = t("clis.detail.subtitleAdded", { title });
  else if (cli.needed_by_servers.length === 0)
    text = t("clis.detail.subtitle", { title, count: cli.needed_by.length });
  else text = t("clis.detail.subtitleNeeded", { title, needed: neededByCount(t, cli) });
  return (
    <>
      <p className="text-sm text-text-muted">{text}</p>
      {cli.description ? <p className="text-sm text-text">{cli.description}</p> : null}
    </>
  );
}

function CliDetail({ cli, onRemoved }: { cli: Cli; onRemoved: () => void }) {
  const { t } = useTranslation();
  const [tab, setTab] = useDetailTab(
    CLI_TABS,
    DEFAULT_CLI_TAB,
    `/clis/${encodeURIComponent(cli.command)}`,
  );
  // Opening the tool reads its help once for this version (a found tool only).
  const iface = useCliInterfaceAuto(cli.command, cli.path !== null);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-mono text-lg font-semibold text-text">{cli.command}</h2>
            <StatusPill tone={cliTone(cli.status)}>{t(`clis.status.${cli.status}`)}</StatusPill>
            {cli.added ? <Badge variant="secondary">{t("clis.kind.added")}</Badge> : null}
          </div>
          <Subtitle cli={cli} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {cli.handoff ? <AgentHandoff prompt={cli.handoff.prompt} /> : null}
          {cli.added ? <CliActions cli={cli} onRemoved={onRemoved} /> : null}
        </div>
      </div>
      <CliProblemBanner cli={cli} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("clis.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="commands">{t("clis.tabs.commands")}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <CliDetailSections cli={cli} />
        </TabsContent>
        <TabsContent value="commands">
          {cli.path ? (
            <CliCommandsTab command={cli.command} iface={iface} />
          ) : (
            <EmptyState
              icon={SquareTerminal}
              title={t("clis.commands.unavailable")}
              description={t("clis.commands.unavailableBody", { command: cli.command })}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

export function CliPane({ command, listed, onRemoved }: Props) {
  const { t } = useTranslation();
  const lookup = useCli(listed ? "" : command);
  const cli = listed ?? lookup.data;

  if (cli) return <CliDetail cli={cli} onRemoved={onRemoved} />;
  if (lookup.isPending) return <PageFallback />;
  return (
    <EmptyState
      icon={SquareTerminal}
      tone="error"
      title={t("clis.detail.notFound")}
      description={lookup.error ? translateApiError(t, lookup.error) : undefined}
    />
  );
}
