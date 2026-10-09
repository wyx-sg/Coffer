// src/components/agents/model/OverviewModelSection.tsx — Overview › Model (boards 2.1.08–2.1.12, 2.1.16).
//
// Provider · Default model · Route, with a Test beside a route through Coffer's
// proxy. "Change…" opens the Change model dialog; `?change-model=1` opens it on
// arrival (Model providers' "Used by" links there) and is dropped when it
// closes.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentBuiltinDefault, useAgentDefaultModel } from "@/lib/hooks/useAgentModels";
import { useProviders } from "@/lib/hooks/useProviders";
import { useModelPairTest } from "@/lib/hooks/useModelTest";
import { activeProviderFor } from "@/lib/providers/usedBy";

import { InfoRow } from "../overview/OverviewParts";
import { useProviderLabel } from "../overview/useProviderLabel";
import { ChangeModelDialog } from "./ChangeModelDialog";

const K = "agents.overviewTab.model";
const PARAM = "change-model";

export function OverviewModelSection({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [openLocal, setOpenLocal] = useState(false);
  const open = openLocal || params.get(PARAM) === "1";
  const close = (next: boolean) => {
    if (next) return setOpenLocal(true);
    setOpenLocal(false);
    if (params.has(PARAM)) {
      const rest = new URLSearchParams(params);
      rest.delete(PARAM);
      setParams(rest, { replace: true });
    }
  };

  const provider = useProviderLabel(agent);
  const providers = useProviders();
  const active = providers.data ? activeProviderFor(agent, providers.data) : null;
  // On its own login the model is whatever the agent's config names; the
  // record's binding is the connection's and may be left over from one.
  const onConnection = !!agent.connection_uid && active !== null;
  const nativeModel = useAgentDefaultModel(onConnection ? "" : agent.type).data ?? null;
  const model = onConnection ? agent.model : nativeModel;
  // The built-in default is named only when the agent itself says which it is.
  const builtinDefault = useAgentBuiltinDefault(onConnection ? "" : agent.type).data ?? null;
  const test = useModelPairTest(active, model ?? "", "chat", agent.type);

  return (
    <Section
      title={t(`${K}.heading`)}
      as="h2"
      actions={
        <Button variant="link" size="sm" onClick={() => close(true)}>
          {t(`${K}.change`)}
        </Button>
      }
    >
      <dl className="flex flex-col">
        <InfoRow label={t(`${K}.provider`)}>
          {provider ?? <Skeleton className="h-4 w-40" />}
        </InfoRow>
        <InfoRow label={t(`${K}.model`)} mono={!!model}>
          {model ??
            (builtinDefault ? t(`${K}.autoNamed`, { model: builtinDefault }) : t(`${K}.auto`))}
        </InfoRow>
        <InfoRow
          label={t(`${K}.route`)}
          trailing={
            active ? (
              <Button
                variant="outline"
                size="sm"
                loading={test.isPending}
                onClick={test.run}
                disabled={!model}
              >
                {t(`${K}.test`)}
              </Button>
            ) : undefined
          }
        >
          {active ? (
            <>
              {t(`${K}.routeProxy`)}
              {test.result?.outcome === "failed" ? (
                <span className="text-danger"> · {test.result.message}</span>
              ) : test.result ? (
                <span> · {t(`${K}.reachable`)}</span>
              ) : null}
            </>
          ) : (
            t(`${K}.routeDirect.${agent.type}`, { agent: agentTypeLabel(agent.type) })
          )}
        </InfoRow>
      </dl>
      <ChangeModelDialog agent={agent} open={open} onOpenChange={close} />
    </Section>
  );
}
