// frontend/src/components/agents/AgentMemoryBulkActions.tsx
// Bulk "import to Coffer" bar for the agent Memory tab's native-memory table.
// Fans out one import-native-memory call per selected store with allSettled (via
// useBulkMutate) so one failure never aborts the rest; a single summary toast
// reports the outcome and the selection clears via onDone(). Imported facts land
// in the matching Coffer project store, so the memory-stores list is refreshed.
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { agentsApi, type NativeMemoryStore } from "@/lib/api/agents";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

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
  const bulk = useBulkMutate({ invalidate: [["memory-stores"]] });

  const runAll = async () => {
    await bulk.run(rows, (s) => agentsApi.importNativeMemory(agentName, s.memory_dir, s.path));
    onDone();
  };

  return (
    <Button size="sm" variant="outline" disabled={bulk.isPending} onClick={() => void runAll()}>
      <Download className="mr-1.5 size-3.5" />
      {t("agents.memoryTab.import")}
    </Button>
  );
}
