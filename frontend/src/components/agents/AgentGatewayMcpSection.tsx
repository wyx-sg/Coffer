// frontend/src/components/agents/AgentGatewayMcpSection.tsx — spec 004 +
// per-agent MCP server scoping.
// Section A of the agent "MCP servers" tab: Coffer's shim install status (the
// install button lives in the page header) plus the EDITABLE scope of MCP
// servers Coffer exposes through the gateway to this agent.
//
//   - mode "auto"     → every enabled mcp_server resource is exposed (default).
//   - mode "selected" → only the checked servers (an explicit allowlist) are.
//
// The enabled mcp_server list is still derived from the global resources, and
// rows click through to the server detail. Extracted from AgentMcpServersTab to
// keep that file inside the component size cap.
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { getAgentMcpScope, putAgentMcpScope, type AgentMcpScope } from "@/lib/api/agents";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import { useAgentMcpStatus } from "@/lib/hooks/useAgents";
import { useResources } from "@/lib/hooks/useResources";

const MCP_KIND = "mcp_server";

type ScopeMode = AgentMcpScope["mode"];

export function AgentGatewayMcpSection({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const status = useAgentMcpStatus(agentName);
  const resources = useResources(MCP_KIND);
  const installed = status.data?.installed ?? false;

  const scopeKey = ["agents", agentName, "mcp-scope"] as const;
  const scope = useQuery({
    queryKey: scopeKey,
    queryFn: () => getAgentMcpScope(agentName),
    // Only fetch once the Coffer shim is installed (the section is hidden
    // otherwise, mirroring the install gate below).
    enabled: !!agentName && installed,
  });

  const saveScope = useMutation({
    mutationFn: (next: AgentMcpScope) => putAgentMcpScope(agentName, next),
    onSuccess: (data) => {
      qc.setQueryData(scopeKey, data);
    },
  });

  // Local edit state, seeded from the loaded scope. `selected` is a Set of the
  // allowlisted server names; it is only meaningful in "selected" mode.
  const [mode, setMode] = useState<ScopeMode>("auto");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (scope.data) {
      setMode(scope.data.mode);
      setSelected(new Set(scope.data.servers));
    }
  }, [scope.data]);

  const enabledServers = useMemo(
    () => (resources.data ?? []).filter((r) => r.kind === MCP_KIND && r.enabled),
    [resources.data],
  );

  const toggleServer = (name: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(name);
      else next.delete(name);
      return next;
    });
  };

  const dirty =
    scope.data !== undefined &&
    (mode !== scope.data.mode ||
      (mode === "selected" &&
        (selected.size !== scope.data.servers.length ||
          scope.data.servers.some((s) => !selected.has(s)))));

  const onSave = () => {
    const servers = mode === "selected" ? Array.from(selected) : [];
    saveScope.mutate({ mode, servers });
  };

  // A 422 (a named server no longer exists) is the documented PUT failure mode;
  // the backend reports it as MCP_SCOPE_SERVER_UNKNOWN. Surface a friendly
  // message for it and fall back to the generic save-error copy (plus the API
  // text) for anything else.
  const saveErrorMessage = (() => {
    if (!saveScope.error) return null;
    const err = saveScope.error;
    if (err instanceof ApiError && err.code === "MCP_SCOPE_SERVER_UNKNOWN") {
      return t("agents.workspace.mcp.unknownServer");
    }
    return `${t("agents.workspace.mcp.saveError")}: ${translateApiError(t, err)}`;
  })();

  // The name + description columns are shared by both modes; "selected" mode
  // prepends a checkbox column for the allowlist toggle.
  const baseColumns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("resources.cols.name"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "description",
      header: t("resources.cols.description"),
      cell: (r) =>
        r.description ? (
          <span className="line-clamp-1 max-w-md text-muted-foreground">{r.description}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];

  const selectModeColumns: Column<ResourceOut>[] = [
    {
      key: "checked",
      header: "",
      className: "w-10 whitespace-nowrap",
      cell: (r) => (
        <Checkbox
          checked={selected.has(r.name)}
          disabled={saveScope.isPending}
          onChange={(e) => toggleServer(r.name, e.currentTarget.checked)}
          aria-label={`${t("agents.workspace.mcp.modeSelected")}: ${r.name}`}
          // Don't let a checkbox click navigate to the server detail.
          onClick={(e) => e.stopPropagation()}
        />
      ),
    },
    ...baseColumns,
  ];

  const goToServer = (r: ResourceOut) =>
    navigate(`/mcp-servers/mcp_server/${r.name}`, {
      state: { backTo: `/agents/${agentName}`, backLabel: agentName },
    });

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-medium text-muted-foreground">
        {t("agents.workspace.mcp.gatewayTitle")}
      </h3>
      {status.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : !installed ? (
        <p className="text-sm text-muted-foreground">{t("agents.mcpTab.notInstalled")}</p>
      ) : resources.isPending || scope.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : resources.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, resources.error)}</p>
      ) : scope.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, scope.error)}</p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="radio"
                name="mcp-scope-mode"
                className="size-4 cursor-pointer accent-primary"
                checked={mode === "auto"}
                disabled={saveScope.isPending}
                onChange={() => setMode("auto")}
              />
              <Label className="cursor-pointer">{t("agents.workspace.mcp.modeAuto")}</Label>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="radio"
                name="mcp-scope-mode"
                className="size-4 cursor-pointer accent-primary"
                checked={mode === "selected"}
                disabled={saveScope.isPending}
                onChange={() => setMode("selected")}
              />
              <Label className="cursor-pointer">{t("agents.workspace.mcp.modeSelected")}</Label>
            </label>
          </div>

          <p className="text-sm text-muted-foreground">
            {mode === "auto"
              ? t("agents.workspace.mcp.modeAutoHint")
              : t("agents.workspace.mcp.modeSelectedHint")}
          </p>

          {enabledServers.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("agents.mcpTab.empty")}</p>
          ) : mode === "selected" ? (
            <DataTable
              rows={enabledServers}
              columns={selectModeColumns}
              rowKey={(r) => r.name}
              search={{ accessor: (r) => r.name, placeholder: t("mcp.table.search") }}
              onRowClick={goToServer}
              emptyMessage={t("agents.mcpTab.empty")}
            />
          ) : (
            <DataTable
              // The servers Coffer exposes to this agent = its enabled servers.
              rows={enabledServers}
              columns={baseColumns}
              rowKey={(r) => r.name}
              search={{ accessor: (r) => r.name, placeholder: t("mcp.table.search") }}
              onRowClick={goToServer}
              emptyMessage={t("agents.mcpTab.empty")}
            />
          )}

          <div className="flex items-center gap-3">
            <Button size="sm" disabled={saveScope.isPending || !dirty} onClick={onSave}>
              {saveScope.isPending ? t("common.saving") : t("agents.workspace.mcp.save")}
            </Button>
            {saveScope.isSuccess && !dirty ? (
              <span className="text-sm text-muted-foreground">
                {t("agents.workspace.mcp.saved")}
              </span>
            ) : null}
            {saveErrorMessage ? (
              <span className="text-sm text-destructive">{saveErrorMessage}</span>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
