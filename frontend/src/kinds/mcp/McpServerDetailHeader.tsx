// frontend/src/kinds/mcp/McpServerDetailHeader.tsx
import { useTranslation } from "react-i18next";
import { Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Trash2 } from "lucide-react";
import { HealthBadge, type HealthState } from "./HealthBadge";
import { EditMcpServerDialog } from "./EditMcpServerDialog";
import type { components } from "@/lib/api/types";

type ResourceOut = components["schemas"]["ResourceOut"];

interface TestResult {
  ok: boolean;
  latency_ms: number;
  protocol_version?: string | null;
  error_message?: string | null;
}

interface Props {
  resource: ResourceOut;
  healthState: HealthState;
  testResult: TestResult | null;
  isTestPending: boolean;
  isEnablePending: boolean;
  isDisablePending: boolean;
  onTestConnection: () => void;
  onToggleEnabled: (checked: boolean) => void;
  onDeleteClick: () => void;
}

export function McpServerDetailHeader({
  resource,
  healthState,
  testResult,
  isTestPending,
  isEnablePending,
  isDisablePending,
  onTestConnection,
  onToggleEnabled,
  onDeleteClick,
}: Props) {
  const { t } = useTranslation();

  return (
    <header className="space-y-2">
      {/* Title + actions stay on one row; the description always sits below
          (never wraps the action cluster down). */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl tracking-tight">{resource.name}</h1>
          <HealthBadge
            state={healthState}
            latencyMs={testResult?.ok ? testResult.latency_ms : undefined}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={onTestConnection} disabled={isTestPending}>
            <Activity className="mr-1.5 size-3.5" />
            {isTestPending ? t("mcp.server.testing") : t("mcp.server.testConnection")}
          </Button>
          <EditMcpServerDialog resource={resource} />
          <Button
            size="sm"
            variant="outline"
            onClick={onDeleteClick}
            aria-label={t("mcp.server.deleteServer")}
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
          </Button>
          <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-card px-3">
            <Switch
              checked={resource.enabled}
              onCheckedChange={onToggleEnabled}
              disabled={isEnablePending || isDisablePending}
              aria-label={resource.enabled ? t("common.enabled") : t("common.disabled")}
            />
            <span className="text-sm font-medium">
              {resource.enabled ? t("common.enabled") : t("common.disabled")}
            </span>
          </div>
        </div>
      </div>
      {resource.description ? (
        <p className="max-w-prose text-sm text-muted-foreground">{resource.description}</p>
      ) : null}
    </header>
  );
}
