// frontend/src/components/mcp/CapabilityBulkActions.tsx
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

import { TableActionButton } from "@/components/table/TableActionButton";
import { capabilitiesApi, type CapabilityType } from "@/lib/hooks/useMcpCapabilityMutations";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

interface RowDescriptor {
  key: string;
}

interface Props {
  serverUid: string;
  kind: CapabilityType;
  rows: RowDescriptor[];
  onDone: () => void;
}

export function CapabilityBulkActions({ serverUid, kind, rows, onDone }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({ invalidate: [mcpCapabilitiesKey(serverUid)] });

  const runAll = async (op: "enable" | "disable") => {
    await bulk.run(rows, (row) =>
      capabilitiesApi.setEnabled(op, {
        serverUid,
        capabilityType: kind,
        capabilityKey: row.key,
      }),
    );
    onDone();
  };

  return (
    <>
      <TableActionButton
        icon={Power}
        label={t("common.bulk.enable")}
        disabled={bulk.isPending}
        onClick={() => void runAll("enable")}
      />
      <TableActionButton
        icon={PowerOff}
        label={t("common.bulk.disable")}
        disabled={bulk.isPending}
        onClick={() => void runAll("disable")}
      />
    </>
  );
}
