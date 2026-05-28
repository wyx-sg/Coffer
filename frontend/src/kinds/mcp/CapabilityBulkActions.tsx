// frontend/src/kinds/mcp/CapabilityBulkActions.tsx
//
// The bulk Enable/Disable action buttons rendered inside the DataTable bulk bar
// for a server's tools / resources / prompts. It receives the currently-selected
// rows and fans out one enable/disable call per row with Promise.allSettled (via
// useBulkMutate) so one failure never aborts the rest; a single summary toast
// reports the outcome and the selection clears via onDone().
//
// Lives in its own file (rather than inline in CapabilityList.tsx) to keep that
// file within its size budget.
import { useTranslation } from "react-i18next";
import { Power, PowerOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { capabilitiesApi, type CapabilityType } from "@/lib/hooks/useMcpCapabilityMutations";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

interface RowDescriptor {
  key: string;
}

interface Props {
  serverName: string;
  kind: CapabilityType;
  rows: RowDescriptor[];
  onDone: () => void;
}

export function CapabilityBulkActions({ serverName, kind, rows, onDone }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({ invalidate: [["mcp", "capabilities", serverName]] });

  const runAll = async (op: "enable" | "disable") => {
    await bulk.run(rows, (row) =>
      capabilitiesApi.setEnabled(op, {
        serverName,
        capabilityType: kind,
        capabilityKey: row.key,
      }),
    );
    onDone();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void runAll("enable")}
      >
        <Power className="mr-1.5 size-3.5" /> {t("common.bulk.enable")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void runAll("disable")}
      >
        <PowerOff className="mr-1.5 size-3.5" /> {t("common.bulk.disable")}
      </Button>
    </>
  );
}
