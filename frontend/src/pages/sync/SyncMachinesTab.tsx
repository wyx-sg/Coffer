// frontend/src/pages/sync/SyncMachinesTab.tsx — Sync → Machines.
//
// The registry (spec vault-sync `## The machine dimension`): every
// installation of Coffer that has converged with this remote, as a derived
// view of `machines/*.yaml` rather than a synced table.
//
// Two notes on this tab are load-bearing rather than decorative:
//
//   * "Last converged" is labelled a DAY, because a machine that is running
//     but idle deliberately does not stamp a heartbeat every round — reading
//     it as an instant would make a healthy machine look stalled.
//   * When `machine_id_is_derived` is false, the id came from a local fallback
//     file rather than from the host, so deleting `~/.coffer` makes this
//     machine reappear under a NEW id — and the old row has to be retired by
//     hand. It is quiet, but it has to be said where the rows are.
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useMachines } from "@/lib/hooks/useMachines";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { SyncMachineRow } from "./SyncMachineRow";

const COLUMNS = [
  "name",
  "system",
  "hostname",
  "version",
  "lastConverged",
  "key",
  "agents",
  "actions",
] as const;

export function SyncMachinesTab() {
  const { t } = useTranslation();
  const { data, isPending } = useMachines();
  const status = useSyncStatus();
  const machines = data?.machines ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sync.machines.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("sync.machines.description")}</p>

        {status.data && !status.data.machine_id_is_derived ? (
          <p className="text-xs text-muted-foreground" data-testid="machine-id-not-derived">
            {t("sync.machines.derivedNote")}
          </p>
        ) : null}

        {isPending ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : machines.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("sync.machines.empty")}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {COLUMNS.map((column) => (
                  <TableHead key={column} className={column === "actions" ? "text-right" : ""}>
                    {t(`sync.machines.columns.${column}`)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {machines.map((machine) => (
                <SyncMachineRow key={machine.machine_id} machine={machine} />
              ))}
            </TableBody>
          </Table>
        )}

        <p className="text-xs text-muted-foreground">{t("sync.machines.lastConvergedHint")}</p>
      </CardContent>
    </Card>
  );
}
