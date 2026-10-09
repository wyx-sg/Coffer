// src/components/agents/AgentHooksTab.tsx — the agent's Hooks tab: the agent's own hooks.
//
// Spec agent-registry "List every hook in the agent's native config". Read
// only: the agent's own hooks as one searchable table that opens a read-only
// details dialog. Coffer installs no hook of its own. A file that does not
// parse is a warning above the table, not a failure of the tab.
import { useTranslation } from "react-i18next";

import { OwnHooksSection } from "@/components/agents/hooks/OwnHooksSection";
import { LoadError } from "@/components/LoadError";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { abbreviateHomePath } from "@/lib/agents/display";
import { ownHooks } from "@/lib/agents/hookRows";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentHooks } from "@/lib/hooks/useAgents";

interface Props {
  agent: AgentOut;
}

export function AgentHooksTab({ agent }: Props) {
  const { t } = useTranslation();
  const hooks = useAgentHooks(agent.uid);
  const own = ownHooks(hooks.data);
  const parseErrors = hooks.data?.parse_errors ?? [];

  if (hooks.error) {
    return <LoadError error={hooks.error} onRetry={() => void hooks.refetch()} />;
  }
  if (hooks.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-8">
      {parseErrors.length > 0 ? (
        <Alert variant="warning">
          <AlertDescription>
            <ul className="space-y-0.5">
              {parseErrors.map((pe) => (
                <li key={`${pe.source}:${pe.path}`} className="break-all">
                  {t("agents.hooks.parseError", {
                    file: abbreviateHomePath(pe.path),
                    error: pe.error,
                  })}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}
      <OwnHooksSection hooks={own} agentType={agent.type} />
    </div>
  );
}
