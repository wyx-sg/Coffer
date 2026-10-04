// src/pages/AgentDetailPage.tsx — one agent, at /agents/<type>[/<tab>] (spec agent-registry, "Offer every agent operation over REST and on the Agents page").
//
// The header (the agent's mark and name, its Coffer state, the action that
// state calls for and the ⋯ menu) over nine tabs addressed by path. The page is
// addressed by the agent's TYPE; `useAgentRoute` turns that into the uid the
// REST routes take. A type that is not added yet still has a page: the header,
// and what adding it takes.
import { useTranslation } from "react-i18next";
import { ArrowLeft, Bot } from "lucide-react";

import { AgentDetailHeader } from "@/components/agents/detail/AgentDetailHeader";
import { AgentDetailTabs } from "@/components/agents/detail/AgentDetailTabs";
import { AgentNotAdded } from "@/components/agents/detail/AgentNotAdded";
import { useAgentRowActions } from "@/components/agents/list/useAgentRowActions";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgentRoute } from "@/lib/hooks/useAgentRoute";
import { Link } from "react-router-dom";

export function AgentDetailPage() {
  const route = useAgentRoute();
  const { t } = useTranslation();

  if (route.isPending) {
    return (
      <div className="space-y-6" aria-busy="true">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-9 w-full" />
      </div>
    );
  }
  // A type that is added but whose record cannot be read is an error, not "not added".
  const unreadable = !!route.typeRow?.uid && !route.agent;
  if (!route.type || !route.typeRow || unreadable) {
    return (
      <EmptyState
        icon={Bot}
        tone={route.error ? "error" : "default"}
        title={t("agents.detail.notFound")}
        description={route.error ? translateApiError(t, route.error) : undefined}
        action={
          <Button variant="outline" size="sm" asChild>
            <Link to="/agents">
              <ArrowLeft aria-hidden className="size-3.5" />
              {t("agents.detail.back")}
            </Link>
          </Button>
        }
      />
    );
  }
  return <AgentDetail typeRow={route.typeRow} route={route} />;
}

function AgentDetail({
  typeRow,
  route,
}: {
  typeRow: AgentTypeOut;
  route: ReturnType<typeof useAgentRoute>;
}) {
  const rowActions = useAgentRowActions(typeRow);
  return (
    <div className="flex min-h-0 flex-col gap-4">
      <AgentDetailHeader typeRow={typeRow} rowActions={rowActions} />
      {route.agent ? (
        <AgentDetailTabs agent={route.agent} typeRow={typeRow} rowActions={rowActions} />
      ) : (
        <AgentNotAdded typeRow={typeRow} rowActions={rowActions} />
      )}
      {rowActions.dialogs}
    </div>
  );
}
