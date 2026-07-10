// frontend/src/components/agents/AgentFacetUnsupported.tsx — the uniform
// "not supported" state for an agent-detail facet the agent's type lacks
// (FR-003a / ADR-042 presentation amendment 2026-07-10): one neutral card in
// place of the tab's normal content — never a functional-looking empty table
// and never a raw error line.
import { Card, CardContent } from "@/components/ui/card";

export function AgentFacetUnsupported({ message, reason }: { message: string; reason?: string }) {
  return (
    <Card>
      <CardContent className="space-y-1 py-6">
        <p className="text-sm text-muted-foreground">{message}</p>
        {reason ? <p className="text-xs text-muted-foreground">{reason}</p> : null}
      </CardContent>
    </Card>
  );
}
