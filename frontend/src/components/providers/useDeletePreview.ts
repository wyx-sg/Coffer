// src/components/providers/useDeletePreview.ts — what deleting a provider would change in agents' config files, as change-preview items.
//
// The daemon computes the exact lines (it runs the same removal the delete
// does, without writing); this only reads them while the review is open and
// shapes them for ChangePreview.
import { useQuery } from "@tanstack/react-query";

import { abbreviateHomePath } from "@/lib/agents/display";
import { providersApi, type ProviderDeletePreview } from "@/lib/api/providers";
import type { ChangeItem } from "@/lib/changePreview/changeCounts";

export function useDeletePreview(uid: string, enabled: boolean) {
  return useQuery({
    queryKey: ["providers", uid, "delete-preview"] as const,
    queryFn: () => providersApi.deletePreview(uid),
    enabled,
    // The review is a snapshot of the files as they are now.
    gcTime: 0,
  });
}

/** The preview's files as ChangePreview items, in agent order. */
export function previewItems(preview: ProviderDeletePreview | undefined): ChangeItem[] {
  return (preview?.agents ?? []).flatMap((agent) =>
    agent.files.map((file, index) => {
      const added = file.diff.filter((l) => l.kind === "add").length;
      const removed = file.diff.filter((l) => l.kind === "remove").length;
      return {
        id: `${agent.agent_uid}:${index}`,
        agentType: agent.agent_type,
        agentName: agent.agent_name,
        path: abbreviateHomePath(file.path),
        op: file.op,
        added,
        removed,
        diff: file.diff.map((l) => ({
          kind: l.kind,
          text: l.text,
          oldNo: l.old_no ?? undefined,
          newNo: l.new_no ?? undefined,
        })),
      } satisfies ChangeItem;
    }),
  );
}
