// frontend/src/kinds/mcp/HealthBadge.tsx
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { healthStatusClass } from "@/lib/statusColors";

export type HealthState = "healthy" | "unknown" | "failing";

interface Props {
  state: HealthState;
  latencyMs?: number;
  className?: string;
}

export function HealthBadge({ state, latencyMs, className }: Props) {
  const { t } = useTranslation();

  const cls = cn(healthStatusClass(state), className);

  const label = t(`mcp.health.${state}`);

  return (
    <Badge className={cls} variant="outline" data-testid="health-badge">
      {label}
      {state === "healthy" && latencyMs !== undefined ? ` · ${latencyMs} ms` : ""}
    </Badge>
  );
}
