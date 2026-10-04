// src/components/agents/overview/OverviewConnection.tsx — the Overview's Connection section (boards 2.1.08–2.1.12).
//
// An unboxed Section: title, "?" tip, one line saying what the connection is,
// then one property row per part (the `coffer` MCP entry and, when listed, the
// memory hook) with where it lives and its health. The state's one fix sits at
// the title's right — Connect, Repair, Turn on (solid) or Check again
// (outline, a Codex hook waiting for approval); a connected agent has none
// (Disconnect lives in the header's ⋯ menu).
import { Trans, useTranslation } from "react-i18next";
import { RefreshCw, Wrench } from "lucide-react";

import { Section } from "@/components/Section";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import { isConnectionCardState, type ConnectionCardState } from "./connectionCopy";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { AgentOut, AgentTypeOut, CofferConnection, CofferHook } from "@/lib/api/agents";

import type { OverviewActions } from "../AgentOverviewTab";
import {
  connectionBodyKey,
  hookAwaitsApproval,
  hookEventCount,
  partHealth,
  partHealthTone,
} from "./connectionCopy";
import { InfoRow, InlineCode, InlinePath, SectionLine } from "./OverviewParts";
import { hookConfigPath, mcpConfigPath } from "./paths";

const K = "agents.overviewTab.connection";

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  state: AgentRowState;
  connection: CofferConnection | undefined;
  hook: CofferHook | null | undefined;
  /** The connection could not be read. */
  failed: boolean;
  actions: OverviewActions;
  /** Re-read the hook's approval (Codex's `/hooks`). */
  onCheckHook: () => void;
  checking: boolean;
}

export function OverviewConnection(props: Props) {
  const { agent, typeRow, state, connection, hook, failed, actions } = props;
  const { t } = useTranslation();
  const title = t(`${K}.heading`);
  const help = <p className="text-xs">{t(`${K}.help`)}</p>;
  if (!isConnectionCardState(state) || !connection) {
    return (
      <Section title={title} help={help} as="h2">
        {failed ? (
          <p className="text-xs text-text-muted">{t(`${K}.loadFailed`)}</p>
        ) : (
          <Skeleton className="h-[120px] w-full rounded-xl" />
        )}
      </Section>
    );
  }
  const awaiting = hookAwaitsApproval(state, hook);
  const files = {
    mcpFile: mcpConfigPath(agent, typeRow),
    hookFile: hookConfigPath(agent, hook?.path),
  };
  return (
    <Section
      title={title}
      help={help}
      as="h2"
      actions={
        <ConnectionFix
          state={state}
          awaiting={awaiting}
          actions={actions}
          onCheckHook={props.onCheckHook}
          checking={props.checking}
        />
      }
    >
      <SectionLine>
        <Trans
          i18nKey={connectionBodyKey(state, connection.parts, hook)}
          values={{ name: agentTypeLabel(agent.type), ...files }}
          components={{ code: <InlineCode /> }}
        />
      </SectionLine>
      <dl className="flex flex-col">
        {connection.parts.map((part) => {
          const health = partHealth(part, hook, state);
          return (
            <InfoRow
              key={part.key}
              label={t(`${K}.part.${part.key === "memory_hook" ? "memoryHook" : "mcp"}`)}
              trailing={
                <StatusWord tone={partHealthTone(health)}>{t(`${K}.health.${health}`)}</StatusWord>
              }
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
            </InfoRow>
          );
        })}
      </dl>
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
  if (!installed || !hook) {
    return (
      <Trans i18nKey={`${K}.part.notIn`} values={{ file }} components={{ path: <InlinePath /> }} />
    );
  }
  // When it last fired is the Hooks tab's to say; this row says where the hook is.
  return (
    <Trans
      i18nKey={`${K}.part.hookIn`}
      count={hookEventCount(hook)}
      values={{ file }}
      components={{ path: <InlinePath /> }}
    />
  );
}

function ConnectionFix({
  state,
  awaiting,
  actions,
  onCheckHook,
  checking,
}: {
  state: ConnectionCardState;
  awaiting: boolean;
  actions: OverviewActions;
  onCheckHook: () => void;
  checking: boolean;
}) {
  const { t } = useTranslation();
  if (awaiting) {
    return (
      <Button variant="outline" size="sm" onClick={onCheckHook} disabled={checking}>
        <RefreshCw aria-hidden />
        {t(`${K}.action.checkAgain`)}
      </Button>
    );
  }
  if (state === "connected") return null;
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
      {t(`${K}.action.${state === "needs_repair" ? "repair" : "connect"}`)}
    </Button>
  );
}
