// frontend/src/lib/hooks/useMcpCapabilityMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

type CapabilityType = "tool" | "resource" | "prompt";

interface ToggleInput {
  serverName: string;
  capabilityType: CapabilityType;
  capabilityKey: string;
}

export function useEnableCapability() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ serverName, capabilityType, capabilityKey }: ToggleInput) => {
      const client = getApiClient();
      const { error } = await client.POST(
        "/resources/mcp_server/{name}/capabilities/{capability_type}/enable",
        {
          params: {
            path: { name: serverName, capability_type: capabilityType },
          },
          body: { capability_key: capabilityKey },
        },
      );
      if (error)
        throw new ApiError(
          error.error?.code ?? "INTERNAL_ERROR",
          error.error?.message ?? "enable capability failed",
        );
    },
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["mcp", "capabilities", vars.serverName] });
    },
  });
}

export function useDisableCapability() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ serverName, capabilityType, capabilityKey }: ToggleInput) => {
      const client = getApiClient();
      const { error } = await client.POST(
        "/resources/mcp_server/{name}/capabilities/{capability_type}/disable",
        {
          params: {
            path: { name: serverName, capability_type: capabilityType },
          },
          body: { capability_key: capabilityKey },
        },
      );
      if (error)
        throw new ApiError(
          error.error?.code ?? "INTERNAL_ERROR",
          error.error?.message ?? "disable capability failed",
        );
    },
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["mcp", "capabilities", vars.serverName] });
    },
  });
}
