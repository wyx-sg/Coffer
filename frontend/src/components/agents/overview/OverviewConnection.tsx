// src/components/agents/overview/OverviewConnection.tsx — the Overview's Connection card (boards 2.1.08, 2.1.09, 2.1.11, 2.1.12).
//
// One icon + state title + one sentence saying what the connection is and what
// its one action does, then one row per part the connection lists (the `coffer`
// MCP entry and, when listed, the memory hook) with where it lives and its
// health. The action opens the page's change preview; Enable is the switch.
import type { ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link2, Power, ShieldAlert, Unlink, Wrench } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import { STATUS_TONE } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import { useConnectFailure } from "@/lib/agents/connectFailure";
import { agentRowTone, type AgentRowState } from "@/lib/agents/rowState";
import type { AgentOut, AgentTypeOut, CofferConnection, CofferHook } from "@/lib/api/agents";
import { toneClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

import type { OverviewActions } from "../AgentOverviewTab";
import { formatLastFired } from "./age";
import { CopyHooksButton } from "../CopyHooksButton";
import {
  connectionBodyKey,
  hookAwaitsApproval,
  hookEventCount,
  isConnectionCardState,
  partHealth,
  partHealthTone,
  repairsOnlyHook,
  type ConnectionCardState,
} from "./connectionCopy";
import { Section } from "@/components/Section";
import { ConnectFailed } from "./ConnectFailed";
import { InlineCode, InlinePath } from "./OverviewParts";
import { hookConfigPath, mcpConfigPath } from "./paths";

const K = "agents.overviewTab.connection";
const ICON = { connected: Link2, not_connected: Unlink, needs_repair: Wrench, disabled: Power };

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  state: AgentRowState;
  connection: CofferConnection | undefined;
  hook: CofferHook | null | undefined;
  /** The connection could not be read. */
  failed: boolean;
  actions: OverviewActions;
}

export function OverviewConnection(props: Props) {
  const { agent, typeRow, state, connection, hook, failed, actions } = props;
  const { t } = useTranslation();
  const connectFailure = useConnectFailure(agent.uid);
  if (!isConnectionCardState(state) || !connection) {
    return (
      <Section title={t(`${K}.heading`)}>
        {failed ? (
          <p className="text-xs text-text-muted">{t(`${K}.loadFailed`)}</p>
        ) : (
          <Skeleton className="h-[120px] w-full rounded-xl" />
        )}
      </Section>
    );
  }
  const awaiting = hookAwaitsApproval(state, hook);
  const Icon = awaiting ? ShieldAlert : ICON[state];
  const tone = awaiting ? "warn" : agentRowTone(state);
  const files = {
    mcpFile: mcpConfigPath(agent, typeRow),
    hookFile: hookConfigPath(agent, hook?.path),
  };
  return (
    <Section title={t(`${K}.heading`)}>
      <Card className="flex flex-col gap-2.5 px-4 py-3.5">
        <div className="flex items-start gap-3">
          <span
            aria-hidden
            className={cn(
              "inline-flex size-[34px] shrink-0 items-center justify-center rounded-lg",
              toneClass(STATUS_TONE[tone]),
            )}
          >
            <Icon className="size-4" />
          </span>
          <div className="flex min-w-0 grow flex-col gap-1">
            <span className="text-sm font-semibold text-text">
              {t(`${K}.title.${awaiting ? "hookUntrusted" : state}`, {
                name: agentTypeLabel(agent.type),
              })}
            </span>
            <span className="text-xs leading-normal text-text-muted">
              <Trans
                i18nKey={connectionBodyKey(state, connection.parts, hook)}
                values={{ name: agentTypeLabel(agent.type), ...files }}
                components={{ code: <InlineCode /> }}
              />
            </span>
          </div>
          {awaiting ? (
            <CopyHooksButton />
          ) : (
            <ConnectionAction
              state={state}
              hookOnly={repairsOnlyHook(connection.parts)}
              actions={actions}
            />
          )}
        </div>
        <div className="ml-[46px] flex flex-col">
          {connection.parts.map((part, i) => (
            <PartRow
              key={part.key}
              first={i === 0}
              label={t(`${K}.part.${part.key === "memory_hook" ? "memoryHook" : "mcp"}`)}
              health={partHealth(part, hook, state === "disabled")}
            >
              {part.key === "memory_hook" ? (
                <HookWhere hook={hook} file={files.hookFile} installed={part.installed} />
              ) : (
                <Trans
                  i18nKey={`${K}.part.${part.installed ? "mcpIn" : "notIn"}`}
                  values={{ file: files.mcpFile }}
                  components={{ code: <InlineCode />, path: <InlinePath /> }}
                />
              )}
            </PartRow>
          ))}
        </div>
        {connectFailure && (state === "not_connected" || state === "needs_repair") ? (
          <ConnectFailed reason={connectFailure} onRetry={() => actions.onConnection("connect")} />
        ) : null}
      </Card>
    </Section>
  );
}

function HookWhere({
  hook,
  file,
  installed,
}: {
  hook: CofferHook | null | undefined;
  file: string;
  installed: boolean;
}) {
  const { t } = useTranslation();
  if (!installed || !hook) {
    return (
      <Trans i18nKey={`${K}.part.notIn`} values={{ file }} components={{ path: <InlinePath /> }} />
    );
  }
  return (
    <>
      <Trans
        i18nKey={`${K}.part.hookIn`}
        values={{ count: hookEventCount(hook), file }}
        components={{ path: <InlinePath /> }}
      />
      {formatLastFired(t, hook.last_fired_at)}
    </>
  );
}

function PartRow({
  label,
  health,
  first,
  children,
}: {
  label: string;
  health: ReturnType<typeof partHealth>;
  first: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        "grid min-h-[34px] grid-cols-[110px_minmax(0,1fr)_auto] items-center gap-3",
        !first && "border-t border-border-subtle",
      )}
    >
      <span className="text-xs text-text-subtle">{label}</span>
      <span className="min-w-0 text-xs text-text-muted">{children}</span>
      <StatusWord tone={partHealthTone(health)}>{t(`${K}.health.${health}`)}</StatusWord>
    </div>
  );
}

function ConnectionAction({
  state,
  hookOnly,
  actions,
}: {
  state: ConnectionCardState;
  /** Only the memory hook is off: the repair names it. */
  hookOnly: boolean;
  actions: OverviewActions;
}) {
  const { t } = useTranslation();
  if (state === "connected") {
    return (
      <Button
        variant="ghost"
        size="sm"
        loading={actions.busy}
        onClick={() => actions.onConnection("disconnect")}
      >
        <Unlink aria-hidden />
        {t(`${K}.action.disconnect`)}
      </Button>
    );
  }
  if (state === "disabled") {
    return (
      <Button size="sm" loading={actions.busy} onClick={actions.onEnable}>
        {t(`${K}.action.enable`)}
      </Button>
    );
  }
  return (
    <Button size="sm" loading={actions.busy} onClick={() => actions.onConnection("connect")}>
      {state === "needs_repair" ? <Wrench aria-hidden /> : null}
      {t(
        `${K}.action.${state === "needs_repair" ? (hookOnly ? "repairHook" : "repair") : "connect"}`,
      )}
    </Button>
  );
}
