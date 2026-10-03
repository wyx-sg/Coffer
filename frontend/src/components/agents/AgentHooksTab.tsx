// src/components/agents/AgentHooksTab.tsx — the agent's Hooks tab: Coffer's memory hook, then the agent's own.
//
// Spec agent-registry "List every hook in the agent's native config". Read
// only. Coffer's memory hook comes first, as one block of properties with its
// fix at the title's right (Repair → the Review changes flow, `onRepair`, wired
// by the detail page; Check again). Below it, the agent's own hooks as one
// searchable table that opens a read-only details dialog. A file that does not
// parse is a warning above both, not a failure of the tab.
import { useTranslation } from "react-i18next";

import { CofferHookSection } from "@/components/agents/hooks/CofferHookSection";
import { OwnHooksSection } from "@/components/agents/hooks/OwnHooksSection";
import { LoadError } from "@/components/LoadError";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { abbreviateHomePath } from "@/lib/agents/display";
import { ownHooks } from "@/lib/agents/hookRows";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentConfigFiles, useAgentHooks } from "@/lib/hooks/useAgents";

interface Props {
  agent: AgentOut;
  /** Opens the Review changes flow that reinstalls Coffer's hook. Repair shows only when given. */
  onRepair?: () => void;
}

export function AgentHooksTab({ agent, onRepair }: Props) {
  const { t } = useTranslation();
  const hooks = useAgentHooks(agent.uid);
  const files = useAgentConfigFiles(agent.uid);
  const own = ownHooks(hooks.data);
  const parseErrors = hooks.data?.parse_errors ?? [];
  const coffer = hooks.data?.coffer_hook ?? null;
  // The Config files entry that holds a hook file, so a path can link to it.
  const fileKeyOf = (path: string) => files.data?.find((f) => f.path === path)?.key ?? null;

  if (hooks.error) {
    return <LoadError error={hooks.error} onRetry={() => void hooks.refetch()} />;
  }
  if (hooks.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
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
      {coffer ? (
        <CofferHookSection
          hook={coffer}
          agentType={agent.type}
          fileKey={fileKeyOf(coffer.path)}
          onRepair={onRepair}
          onCheckAgain={() => void hooks.refetch()}
          checking={hooks.isFetching}
        />
      ) : null}
      <OwnHooksSection hooks={own} agentType={agent.type} fileKeyOf={fileKeyOf} />
    </div>
  );
}
