// frontend/src/lib/hooks/useMcpInvocations.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError, translateApiError } from "@/lib/api/errors";
import { useToast } from "@/components/ui/toast";
import type { components } from "@/lib/api/types";

type InvocationListOut = components["schemas"]["InvocationListOut"];

export type InvocationStatusFilter = "ok" | "error" | "timeout" | "denied";

interface UseMcpInvocationsArgs {
  serverName: string;
  limit?: number;
  status?: InvocationStatusFilter;
  since?: string;
  enabled?: boolean;
}

export type McpServerStatus = "healthy" | "failing";

/**
 * Card-level status of a server — a cheap backend read of persisted
 * state (discovered capabilities + last invocation), no subprocess
 * spawn. `null` = nothing known yet, so the card shows no badge.
 */
export function useMcpServerStatus(serverName: string) {
  return useQuery({
    queryKey: ["mcp", "status", serverName],
    queryFn: async (): Promise<McpServerStatus | null> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/mcp_server/{name}/status", {
        params: { path: { name: serverName } },
      });
      if (error || !data) return null;
      return data.status === "unknown" ? null : data.status;
    },
  });
}

/** The stdio launcher missing on THIS machine (synced server, runner not
 * installed here), if any — rendered as "missing <runner>" + one-click
 * install when the runner has an allowlisted formula. */
export function useMcpServerRunner(serverName: string) {
  return useQuery({
    queryKey: ["mcp", "runner", serverName],
    queryFn: async () => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/mcp_server/{name}/status", {
        params: { path: { name: serverName } },
      });
      if (error || !data) return null;
      return {
        missingRunner: data.missing_runner ?? null,
        installable: data.runner_installable ?? false,
      };
    },
  });
}

export function useInstallMcpRunner() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async (serverName: string) => {
      const client = getApiClient();
      const { data, error } = await client.POST("/resources/mcp_server/{name}/install-runner", {
        params: { path: { name: serverName } },
      });
      if (error) throwApiError(error, "MCP_RUNNER_INSTALL_FAILED", "runner install failed");
      return data;
    },
    onSuccess: (_data, serverName) => {
      void qc.invalidateQueries({ queryKey: ["mcp", "runner", serverName] });
      void qc.invalidateQueries({ queryKey: ["mcp", "status", serverName] });
    },
    // A failed brew run carries its stderr tail in the error message — it
    // must reach the user, not vanish into a button flip (review #294).
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useMcpInvocations({
  serverName,
  limit = 50,
  status,
  since,
  enabled = true,
}: UseMcpInvocationsArgs) {
  return useQuery({
    queryKey: ["mcp", "invocations", serverName, { limit, status, since }],
    queryFn: async (): Promise<InvocationListOut> => {
      const client = getApiClient();
      const query: Record<string, string | number> = { limit };
      if (status) query.status = status;
      if (since) query.since = since;
      const { data, error } = await client.GET("/resources/mcp_server/{name}/invocations", {
        params: {
          path: { name: serverName },
          query: query as never,
        },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "list invocations failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty invocations response");
      return data;
    },
    enabled,
    // Invocation history is append-only audit data, not a live console, so a
    // slower poll suffices.
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}
