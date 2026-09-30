// src/components/agents/model/AgentModelTab.tsx — the agent's Model tab, the only place its provider is switched: Provider, Model, Effort, Model per tier, Test connection, and the Review pane.
//
// Under the provider, Fallback and Proxy token say how the applied provider is
// reached (ProxyRows). Everything on the left is a draft (useAgentConnectionDraft); the right pane
// says what confirming would write and holds Confirm switch (spec
// provider-switching "Offer every connection operation on REST, CLI and web").
import { useTranslation } from "react-i18next";
import { Loader2, PlugZap } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import type { AgentOut } from "@/lib/api/agents";
import { BUILTIN, useAgentConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";
import { ModelFields } from "./ModelFields";
import { ProviderChoices } from "./ProviderChoices";
import { ProxyRows } from "./ProxyRows";
import { SwitchReview } from "./SwitchReview";
import { TierSection } from "./TierSection";

interface Props {
  agent: AgentOut;
}

export function AgentModelTab({ agent }: Props) {
  const { t } = useTranslation();
  const c = useAgentConnectionDraft(agent);

  return (
    <div className="flex flex-col gap-8 lg:flex-row">
      <div className="flex min-w-0 flex-[1.2_1_0] flex-col gap-[22px]">
        <ProviderChoices
          agentType={agent.type}
          connections={c.compatible}
          value={c.draftConn}
          applied={c.appliedConn}
          disabled={c.busy || c.loading}
          onChange={c.pickConnection}
        />
        <ProxyRows
          agent={agent}
          model={agent.model ?? null}
          onProvider={c.appliedConn !== BUILTIN}
        />
        <ModelFields agentType={agent.type} draft={c} />
        {c.showTiers ? <TierSection draft={c} /> : null}
        {!c.draftIsBuiltin ? (
          <div className="flex flex-wrap items-center gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={c.runTest}
              disabled={!c.draftModel || c.testPending || c.busy}
            >
              {c.testPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <PlugZap aria-hidden />
              )}
              {t("agents.modelTab.test")}
            </Button>
            {c.testResult ? (
              <span role="status">
                <StatusWord tone={c.testResult.ok ? "ok" : "err"} className="whitespace-normal">
                  {c.testResult.message}
                </StatusWord>
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="min-w-0 flex-[1_1_0] lg:self-start">
        <SwitchReview agent={agent} draft={c} />
      </div>
    </div>
  );
}
