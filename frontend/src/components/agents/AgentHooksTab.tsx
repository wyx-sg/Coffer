// frontend/src/components/agents/AgentHooksTab.tsx — spec agent-registry
// "List every hook in the agent's native config".
//
// "Hooks" tab on the agent detail page, read-only: every command hook the
// agent's own config files and its enabled plugins declare, grouped by event.
// A row shows the matcher ("all" when there is none), the command (truncated,
// full text on hover), where it is declared (the user's config or a plugin) and
// open / reveal for that file — Coffer edits none of these hooks. Coffer's own
// delivery hook carries a "Coffer" badge, and its health sits in one line above
// the list (AgentCofferHookStatus). A file that would not parse is a warning,
// not a failure of the whole tab.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Webhook } from "lucide-react";

import { AgentCofferHookStatus } from "@/components/agents/AgentCofferHookStatus";
import { EmptyState } from "@/components/EmptyState";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { AgentOut, NativeHook } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useAgentHooks } from "@/lib/hooks/useAgents";

/** Hooks grouped by event, in the order the daemon listed them. */
function groupByEvent(items: NativeHook[]): [string, NativeHook[]][] {
  const groups = new Map<string, NativeHook[]>();
  for (const h of items) {
    const list = groups.get(h.event);
    if (list) list.push(h);
    else groups.set(h.event, [h]);
  }
  return [...groups.entries()];
}

/** Open-in-editor / reveal for the file that declares a hook, as icon buttons. */
function HookFileActions({ path }: { path: string }) {
  const items = useFileActionItems(path);
  return (
    <span className="flex shrink-0 items-center">
      {items.map((it) => {
        const Icon = it.icon;
        return (
          <Tooltip key={it.key}>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={it.label}
                onClick={it.onClick}
              >
                <Icon className="size-3.5" aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{it.label}</TooltipContent>
          </Tooltip>
        );
      })}
    </span>
  );
}

function HookRow({ hook }: { hook: NativeHook }) {
  const { t } = useTranslation();
  return (
    <li className="flex items-center gap-3 px-4 py-2 text-sm">
      <span className="w-32 shrink-0 truncate font-mono text-xs text-muted-foreground">
        {hook.matcher || t("agents.hooksTab.allMatcher")}
      </span>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="min-w-0 flex-1 truncate font-mono text-xs">{hook.command}</span>
        </TooltipTrigger>
        <TooltipContent className="max-w-lg break-all font-mono">{hook.command}</TooltipContent>
      </Tooltip>
      {hook.coffer ? <Badge variant="secondary">{t("agents.hooksTab.cofferBadge")}</Badge> : null}
      <span className="w-40 shrink-0 truncate text-xs text-muted-foreground">
        {hook.source === "plugin"
          ? t("agents.hooksTab.sourcePlugin", { id: hook.plugin ?? "" })
          : t("agents.hooksTab.sourceUser")}
      </span>
      <HookFileActions path={hook.path} />
    </li>
  );
}

export function AgentHooksTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const hooks = useAgentHooks(agent.uid);
  const groups = useMemo(() => groupByEvent(hooks.data?.items ?? []), [hooks.data]);

  if (hooks.isPending) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label={t("common.loading")}>
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (hooks.error) {
    return <p className="text-sm text-destructive">{translateApiError(t, hooks.error)}</p>;
  }

  const { coffer_hook: cofferHook, parse_errors: parseErrors } = hooks.data;

  return (
    <TooltipProvider>
      <div className="space-y-3">
        {cofferHook ? <AgentCofferHookStatus agentUid={agent.uid} hook={cofferHook} /> : null}

        {parseErrors.length > 0 ? (
          <Alert variant="warning">
            <AlertDescription>
              <p className="font-medium">{t("agents.hooksTab.parseError")}</p>
              <ul className="mt-1 space-y-0.5">
                {parseErrors.map((pe) => (
                  <li key={`${pe.source}:${pe.path}`} className="break-all font-mono text-xs">
                    {pe.path}: {pe.error}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}

        {groups.length === 0 ? (
          <EmptyState
            icon={Webhook}
            title={t("agents.hooksTab.emptyTitle")}
            description={t("agents.hooksTab.emptyBody")}
          />
        ) : (
          groups.map(([event, rows]) => (
            <Card key={event} className="overflow-hidden">
              <h3 className="border-b bg-surface-sunken px-4 py-2 font-mono text-sm font-medium">
                {event}
              </h3>
              <ul className="divide-y" aria-label={event}>
                {rows.map((h, i) => (
                  <HookRow key={`${h.path}:${h.matcher ?? ""}:${h.command}:${i}`} hook={h} />
                ))}
              </ul>
            </Card>
          ))
        )}
      </div>
    </TooltipProvider>
  );
}
