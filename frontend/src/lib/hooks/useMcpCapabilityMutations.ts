// frontend/src/lib/hooks/useMcpCapabilityMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { mcpServersApi, type CapabilityType } from "@/lib/api/mcpServers";
import { translateApiError } from "@/lib/api/errors";
import { useToast } from "@/components/ui/toast";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";

interface ToggleInput {
  serverUid: string;
  capabilityType: CapabilityType;
  capabilityKey: string;
}

/**
 * Direct enable/disable calls for a single capability, shared by the per-row
 * ToggleSwitch (via the hooks below) and the bulk fan-out (CapabilityBulkActions
 * via useBulkMutate) so both hit one request. Throws an ApiError on a non-2xx.
 */
export const capabilitiesApi = {
  setEnabled: (op: "enable" | "disable", input: ToggleInput): Promise<void> =>
    mcpServersApi.setCapabilityEnabled(
      op,
      input.serverUid,
      input.capabilityType,
      input.capabilityKey,
    ),
};

export function useEnableCapability() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: ToggleInput) => capabilitiesApi.setEnabled("enable", input),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: mcpCapabilitiesKey(vars.serverUid) });
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
      void qc.invalidateQueries({ queryKey: mcpCapabilitiesKey(vars.serverUid) });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
