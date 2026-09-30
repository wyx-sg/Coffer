// src/components/clis/CliPane.tsx — the CLIs page's detail pane: one required command.
//
// Spec web-ui "Show every CLI a skill requires on the CLIs page". The header
// names the command with its status pill and "<title> · needed by N skills"
// (or "… by 1 MCP server and 1 skill" for a launcher MCP servers start with),
// and — for a command that needs the person (missing, too old, not logged in)
// — its one action: the daemon's hand-off prompt (AgentHandoff). Then the
// problem banner and the Command / Login / Needed by sections. A command not
// in the list (a deep link the list has not caught up with) is read on its own.
import { SquareTerminal } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { PageFallback } from "@/components/PageFallback";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { StatusPill } from "@/components/status/StatusPill";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { cliTone, neededByCount } from "@/lib/clis/format";
import { useCli } from "@/lib/hooks/useClis";
import { CliDetailSections } from "./CliDetailSections";
import { CliProblemBanner } from "./CliProblemBanner";

interface Props {
  command: string;
  /** The command's row from the list, when the list has it. */
  listed: Cli | undefined;
}

function CliDetail({ cli }: { cli: Cli }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-mono text-lg font-semibold text-text">{cli.command}</h2>
            <StatusPill tone={cliTone(cli.status)}>{t(`clis.status.${cli.status}`)}</StatusPill>
          </div>
          <p className="text-sm text-text-muted">
            {cli.needed_by_servers.length === 0
              ? t("clis.detail.subtitle", {
                  title: cli.title ?? cli.command,
                  count: cli.needed_by.length,
                })
              : t("clis.detail.subtitleNeeded", {
                  title: cli.title ?? cli.command,
                  needed: neededByCount(t, cli),
                })}
          </p>
        </div>
        {cli.handoff ? <AgentHandoff prompt={cli.handoff.prompt} /> : null}
      </div>
      <CliProblemBanner cli={cli} />
      <CliDetailSections cli={cli} />
    </div>
  );
}

export function CliPane({ command, listed }: Props) {
  const { t } = useTranslation();
  const lookup = useCli(listed ? "" : command);
  const cli = listed ?? lookup.data;

  if (cli) return <CliDetail cli={cli} />;
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
