// frontend/src/lib/hooks/useCallContent.ts
//
// A tool call's recorded content, read when its drawer opens, and the switch
// that decides whether calls record it (spec mcp-gateway "Record invocations
// with redacted, bounded content", "Switch call content recording per machine").
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { callContentApi, fetchCall } from "@/lib/api/activity";
import { activityCallKey, callContentSettingKey } from "@/lib/api/queryKeys";

/** One call by id; a recorded call never changes, so it is read once. */
export function useCallDetail(id: number) {
  return useQuery({
    queryKey: activityCallKey(id),
    queryFn: ({ signal }) => fetchCall(id, signal),
    staleTime: Infinity,
  });
}

export function useCallContentSetting() {
  return useQuery({ queryKey: callContentSettingKey, queryFn: callContentApi.get });
}

export function useSetCallContent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => callContentApi.set(enabled),
    onSuccess: (data) => qc.setQueryData(callContentSettingKey, data),
  });
}
