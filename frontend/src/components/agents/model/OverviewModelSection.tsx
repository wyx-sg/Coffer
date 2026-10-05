// src/components/agents/model/OverviewModelSection.tsx — Overview › Model (boards 2.1.08–2.1.12, 2.1.16).
//
// Provider · Default model · Route, with a Test beside a route through Coffer's
// proxy. "Change…" opens the Change model dialog; `?change-model=1` opens it on
// arrival (Model providers' "Used by" links there) and is dropped when it
// closes. With the Models feature off the section is read-only: no Provider
// row, no Change.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentDefaultModel } from "@/lib/hooks/useAgentModels";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
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
  const models = useFeatureEnabled("models") === true;
  const [params, setParams] = useSearchParams();
  const [openLocal, setOpenLocal] = useState(false);
  const open = models && (openLocal || params.get(PARAM) === "1");
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
  const providers = useProviders(models);
  const active = providers.data ? activeProviderFor(agent, providers.data) : null;
  // On its own login the model is whatever the agent's config names; the
  // record's binding is the connection's and may be left over from one.
  const onConnection = !!agent.connection_uid && active !== null;
  const nativeModel = useAgentDefaultModel(onConnection ? "" : agent.type).data ?? null;
  const model = onConnection ? agent.model : nativeModel;
  const test = useModelPairTest(active, model ?? "");

  return (
    <Section
      title={t(`${K}.heading`)}
      as="h2"
      actions={
        models ? (
          <Button variant="link" size="sm" onClick={() => close(true)}>
            {t(`${K}.change`)}
          </Button>
        ) : undefined
      }
    >
      <dl className="flex flex-col">
        {models ? (
          <InfoRow label={t(`${K}.provider`)}>
            {provider ?? <Skeleton className="h-4 w-40" />}
          </InfoRow>
        ) : null}
        <InfoRow label={t(`${K}.model`)} mono={!!model}>
          {model ?? t(`${K}.auto`)}
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
      {models ? <ChangeModelDialog agent={agent} open={open} onOpenChange={close} /> : null}
    </Section>
  );
}
