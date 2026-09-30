// src/components/agents/overview/useDetectionCheck.ts — when detection last read the machine, and a way to read it again.
//
// Detection is the types query every agent page reads (useAgentTypes); Check
// again refetches it, and its read time is the problem cards' "Checked at 09:12".
import { useAgentTypes } from "@/lib/hooks/useAgents";
import { formatLocalDateTime } from "@/lib/utils";

export function useDetectionCheck() {
  const types = useAgentTypes();
  const at = types.dataUpdatedAt ? formatLocalDateTime(new Date(types.dataUpdatedAt)) : "";
  return {
    checkedAt: at.slice(11, 16),
    checking: types.isFetching,
    check: () => void types.refetch(),
  };
}
