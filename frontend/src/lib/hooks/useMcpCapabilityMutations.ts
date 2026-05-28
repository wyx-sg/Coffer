// frontend/src/lib/hooks/useMcpCapabilityMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getApiClient } from "@/lib/api/client";
import { throwApiError, translateApiError } from "@/lib/api/errors";
import { useToast } from "@/components/ui/toast";

export type CapabilityType = "tool" | "resource" | "prompt";

interface ToggleInput {
  serverName: string;
  capabilityType: CapabilityType;
  capabilityKey: string;
}

/**
 * Direct enable/disable calls for a single capability, shared by the per-row
 * ToggleSwitch (via the hooks below) and the bulk fan-out (CapabilityBulkActions
 * via useBulkMutate) so both hit one request. Throws an ApiError on a non-2xx.
 */
export const capabilitiesApi = {
  setEnabled: async (op: "enable" | "disable", input: ToggleInput): Promise<void> => {
    const { serverName, capabilityType, capabilityKey } = input;
    const { error } = await getApiClient().POST(
      `/resources/mcp_server/{name}/capabilities/{capability_type}/${op}` as
        | "/resources/mcp_server/{name}/capabilities/{capability_type}/enable"
        | "/resources/mcp_server/{name}/capabilities/{capability_type}/disable",
      {
        params: { path: { name: serverName, capability_type: capabilityType } },
        body: { capability_key: capabilityKey },
      },
    );
    if (error) throwApiError(error, "INTERNAL_ERROR", `${op} capability failed`);
  },
};

export function useEnableCapability() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: ToggleInput) => capabilitiesApi.setEnabled("enable", input),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["mcp", "capabilities", vars.serverName] });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useDisableCapability() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: ToggleInput) => capabilitiesApi.setEnabled("disable", input),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["mcp", "capabilities", vars.serverName] });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
