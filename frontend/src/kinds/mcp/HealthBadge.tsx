// frontend/src/kinds/mcp/HealthBadge.tsx
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type HealthState = "healthy" | "unknown" | "failing";

interface Props {
  state: HealthState;
  latencyMs?: number;
  className?: string;
}

export function HealthBadge({ state, latencyMs, className }: Props) {
  const { t } = useTranslation();

  const cls = cn(
    state === "healthy" && "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
    state === "failing" && "bg-destructive/10 text-destructive",
    state === "unknown" && "bg-muted text-muted-foreground",
    className,
  );

  const label = t(`mcp.health.${state}`);

  return (
    <Badge className={cls} variant="outline" data-testid="health-badge">
      {label}
      {state === "healthy" && latencyMs !== undefined ? ` · ${latencyMs} ms` : ""}
    </Badge>
  );
}
