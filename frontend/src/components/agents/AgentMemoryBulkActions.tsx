// frontend/src/components/agents/AgentMemoryBulkActions.tsx
// Bulk "import to Coffer" bar for the agent Memory tab's native-memory table.
// Enqueues one async batch-import call for the selected stores (returns 202 at
// once) so the import runs off the request path; a summary toast reports how many
// were queued and the per-row status column then polls to completion. The
// selection clears via onDone(). Imported facts land in the matching Coffer
// project store, so the memory-stores list is refreshed by the hook.
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { NativeMemoryStore } from "@/lib/api/agents";
import { useImportNativeMemoryBatch } from "@/lib/hooks/useAgents";

export function AgentNativeMemoryBulkActions({
  agentName,
  rows,
  onDone,
}: {
  agentName: string;
  rows: NativeMemoryStore[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const batch = useImportNativeMemoryBatch(agentName);

  const runAll = () =>
    batch.mutate(
      rows.map((s) => s.memory_dir),
      {
        onSuccess: (r) => {
          toast.success(t("agents.memoryTab.importQueued", { count: r.queued }));
          onDone();
        },
        onError: (e) => toast.error(translateApiError(t, e)),
      },
    );

  return (
    <Button size="sm" variant="outline" disabled={batch.isPending} onClick={runAll}>
      <Download className="mr-1.5 size-3.5" />
      {t("agents.memoryTab.import")}
    </Button>
  );
}
