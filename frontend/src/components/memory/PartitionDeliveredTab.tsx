// frontend/src/components/memory/PartitionDeliveredTab.tsx — what each agent is handed at session start here.
//
// The partition's Delivered tab (`/memory/<uid>/delivered`, web-ui "Show
// memory delivery on the Memory page"): the exact session-start text each
// connected agent receives in this partition's project, composed by the
// daemon the same way the hook composes it. Read-only, with a switch between
// agents (Claude Code first) and Copy. No hook state: installed, stale and
// Repair live on the agent's own page.
import { useState } from "react";
import { Copy, Send } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { EmptyState } from "@/components/EmptyState";
import { FILE_PANE_SCROLL, useFillToBottom } from "@/components/filePane";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath } from "@/lib/agents/display";
import { translateApiError } from "@/lib/api/errors";
import { useMemoryDelivered } from "@/lib/hooks/useMemory";
import { cn } from "@/lib/utils";

interface Props {
  uid: string;
  /** The repository the partition is keyed on; empty for `global`. */
  repositoryPath: string;
}

export function PartitionDeliveredTab({ uid, repositoryPath }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const delivered = useMemoryDelivered(uid);
  const fill = useFillToBottom();
  const [chosen, setChosen] = useState<string | null>(null);

  if (delivered.isPending) {
    return (
      <div className="space-y-2" aria-busy="true">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (delivered.error) {
    return (
      <EmptyState
        icon={Send}
        tone="error"
        title={t("memory.delivered.loadFailed")}
        description={translateApiError(t, delivered.error)}
      />
    );
  }

  const agents = sortAgents(
    (delivered.data ?? []).map((a) => ({ ...a, type: a.agent_type, name: a.agent_name })),
  );
  if (agents.length === 0) {
    return <EmptyState icon={Send} title={t("memory.delivered.none")} />;
  }
  const current = agents.find((a) => a.agent_uid === chosen) ?? agents[0];
  const copy = () =>
    void navigator.clipboard
      ?.writeText(current.text)
      .then(() => toast.success(t("common.copied")))
      .catch(() => undefined);

  return (
    <div ref={fill.ref} style={fill.style} className="flex min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div
          role="radiogroup"
          aria-label={t("memory.delivered.agentsLabel")}
          className="inline-flex rounded-md border border-border-subtle p-0.5"
        >
          {agents.map((a) => {
            const active = a.agent_uid === current.agent_uid;
            return (
              <button
                key={a.agent_uid}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setChosen(a.agent_uid)}
                className={cn(
                  "inline-flex h-control-sm items-center gap-1.5 rounded-sm px-2.5 text-xs",
                  active
                    ? "bg-surface-selected font-label text-text"
                    : "text-text-muted hover:bg-surface-hover",
                )}
              >
                <AgentBadge type={a.agent_type} name={a.agent_name} size="sm" tooltip={false} />
                {a.agent_name}
              </button>
            );
          })}
        </div>
        <span className="text-xs text-text-muted">
          {repositoryPath
            ? t("memory.delivered.intro", { path: abbreviateHomePath(repositoryPath) })
            : t("memory.delivered.introGlobal")}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <span className="text-xs text-text-muted tabular-nums">
            {t("memory.delivered.characters", { count: current.text.length })}
          </span>
          <Button type="button" variant="outline" size="sm" onClick={copy}>
            <Copy className="mr-1.5 size-3.5" aria-hidden />
            {t("memory.delivered.copy")}
          </Button>
        </span>
      </div>
      <pre
        data-testid="memory-delivered-text"
        className={cn(
          FILE_PANE_SCROLL,
          "whitespace-pre-wrap rounded-lg border border-border-subtle bg-surface-sunken p-3 font-mono text-xs text-text",
        )}
      >
        {current.text}
      </pre>
    </div>
  );
}
