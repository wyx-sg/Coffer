// src/components/agents/overview/OverviewConnection.tsx — the Overview's Connection section (boards 2.1.08–2.1.12).
//
// An unboxed Section: title, "?" tip, one line saying what the connection is,
// then one property row per part (the `coffer` MCP entry) with where it lives
// and its health. The state's one fix sits at the title's right — Connect or
// Repair; a connected agent has none (Disconnect lives in the header's ⋯ menu).
import { Trans, useTranslation } from "react-i18next";
import { Wrench } from "lucide-react";

import { Section } from "@/components/Section";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import { isConnectionCardState, type ConnectionCardState } from "./connectionCopy";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { AgentOut, AgentTypeOut, CofferConnection } from "@/lib/api/agents";

import type { OverviewActions } from "../AgentOverviewTab";
import { connectionBodyKey, partHealth, partHealthTone } from "./connectionCopy";
import { InfoRow, InlineCode, InlinePath, SectionLine } from "./OverviewParts";
import { mcpConfigPath } from "./paths";

const K = "agents.overviewTab.connection";

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  state: AgentRowState;
  connection: CofferConnection | undefined;
  /** The connection could not be read. */
  failed: boolean;
  actions: OverviewActions;
}

export function OverviewConnection(props: Props) {
  const { agent, typeRow, state, connection, failed, actions } = props;
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
  const mcpFile = mcpConfigPath(agent, typeRow);
  return (
    <Section
      title={title}
      help={help}
      as="h2"
      actions={<ConnectionFix state={state} actions={actions} />}
    >
      <SectionLine>
        <Trans
          i18nKey={connectionBodyKey(state)}
          values={{ name: agentTypeLabel(agent.type), mcpFile }}
          components={{ code: <InlineCode /> }}
        />
      </SectionLine>
      <dl className="flex flex-col">
        {connection.parts.map((part) => {
          const health = partHealth(part, state);
          return (
            <InfoRow
              key={part.key}
              label={t(`${K}.part.mcp`)}
              trailing={
                <StatusWord tone={partHealthTone(health)}>{t(`${K}.health.${health}`)}</StatusWord>
              }
            >
              <Trans
                i18nKey={`${K}.part.${part.installed ? "mcpIn" : "notIn"}`}
                values={{ file: mcpFile }}
                components={{ code: <InlineCode />, path: <InlinePath /> }}
              />
            </InfoRow>
          );
        })}
      </dl>
    </Section>
  );
}

function ConnectionFix({
  state,
  actions,
}: {
  state: ConnectionCardState;
  actions: OverviewActions;
}) {
  const { t } = useTranslation();
  if (state === "connected") return null;
  return (
    <Button size="sm" loading={actions.busy} onClick={() => actions.onConnection("connect")}>
      {state === "needs_repair" ? <Wrench aria-hidden /> : null}
      {t(`${K}.action.${state === "needs_repair" ? "repair" : "connect"}`)}
    </Button>
  );
}
