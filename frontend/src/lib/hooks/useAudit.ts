// frontend/src/lib/hooks/useAudit.ts
import { useQuery } from "@tanstack/react-query";
import { fetchAuditPage } from "@/lib/api/activity";
import { auditListKey } from "@/lib/api/queryKeys";

interface UseAuditArgs {
  kind?: string;
  eventType?: string;
  since?: string;
  limit?: number;
  /** False switches the lane off entirely — no request, no discarded response. */
  enabled?: boolean;
}

export function useAudit(args: UseAuditArgs) {
  const { kind, eventType, since, limit = 50, enabled = true } = args;
  return useQuery({
    queryKey: auditListKey({ kind, eventType, since, limit }),
    queryFn: () => fetchAuditPage({ kind, eventType, since }, limit),
    enabled,
  });
}
