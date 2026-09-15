// frontend/src/kinds/mcp/McpServerDetailHeader.tsx
//
// The server's detail header: the shared PageHeader with the health badge
// beside the name, the description beneath, and the actions in the fixed
// detail-page order — reach, test, edit, delete.
import { useTranslation } from "react-i18next";
import { Activity, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { Button } from "@/components/ui/button";
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
  /** Where "← back" leads; the list by default, or the agent page that sent
   *  the reader here. */
  back: { to: string; label: string };
  healthState: HealthState;
  testResult: TestResult | null;
  isTestPending: boolean;
  onTestConnection: () => void;
  onDeleteClick: () => void;
}

export function McpServerDetailHeader({
  resource,
  back,
  healthState,
  testResult,
  isTestPending,
  onTestConnection,
  onDeleteClick,
}: Props) {
  const { t } = useTranslation();

  return (
    <PageHeader
      back={back}
      title={resource.name}
      subtitle={resource.description || undefined}
      badges={
        <HealthBadge
          state={healthState}
          latencyMs={testResult?.ok ? testResult.latency_ms : undefined}
        />
      }
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <ScopeControl kind="mcp_server" name={resource.name} enabled={resource.enabled} />
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
        </div>
      }
    />
  );
}
