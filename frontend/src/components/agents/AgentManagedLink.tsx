// frontend/src/components/agents/AgentManagedLink.tsx
// Shared "managed by Coffer → open the standalone page" pointer, so the
// Memory / MCP / Skill agent-detail tabs read with one visual language: a muted
// section heading + hint on the left, an outline link button on the right.
//
// Memory and MCP render <ManagedLinkCard> (the row in its own Card); the Skill
// tab embeds <ManagedLinkRow> inside its follow-toggle card so the toggle and
// the pointer share a single white box.
//
// <CofferGatewayCard> wraps that pointer for surfaces an agent reaches THROUGH
// the Coffer MCP gateway (its Coffer memory, its gateway MCP servers): when
// Coffer MCP isn't installed on the agent those surfaces are unreachable, so the
// card shows the shared "Coffer MCP not installed" note instead of the link.
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAgentMcpStatus } from "@/lib/hooks/useAgents";

export interface ManagedLinkProps {
  /** Muted section heading, e.g. "Managed by Coffer" / "Via Coffer gateway". */
  title: string;
  /** One-line explanation of why the resource is managed elsewhere. */
  hint: string;
  /** Button label, e.g. "Open the Memory page". */
  buttonLabel: string;
  /** Navigate to the standalone management page. */
  onOpen: () => void;
}

export function ManagedLinkRow({ title, hint, buttonLabel, onOpen }: ManagedLinkProps) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0 space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <Button variant="outline" size="sm" className="shrink-0" onClick={onOpen}>
        {buttonLabel}
        <ArrowRight className="ml-1.5 size-3.5" />
      </Button>
    </div>
  );
}

export function ManagedLinkCard(props: ManagedLinkProps) {
  return (
    <Card className="p-4">
      <ManagedLinkRow {...props} />
    </Card>
  );
}

/** A ManagedLinkCard gated on whether Coffer MCP is installed on the agent.
 * The surface is reached through the Coffer MCP gateway, so until the agent has
 * Coffer MCP installed it shows the "not installed" note instead of the link. */
export function CofferGatewayCard({
  agentName,
  notInstalledHint,
  ...link
}: ManagedLinkProps & { agentName: string; notInstalledHint: string }) {
  const { t } = useTranslation();
  const status = useAgentMcpStatus(agentName);
  const installed = status.data?.installed ?? false;

  if (installed) {
    return <ManagedLinkCard {...link} />;
  }
  return (
    <Card className="space-y-1 p-4">
      <h3 className="text-sm font-medium text-muted-foreground">{link.title}</h3>
      <p className="text-sm text-muted-foreground">
        {status.isPending ? t("common.loading") : notInstalledHint}
      </p>
    </Card>
  );
}
