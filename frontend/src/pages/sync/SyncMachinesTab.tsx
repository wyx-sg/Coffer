// frontend/src/pages/sync/SyncMachinesTab.tsx — Sync → Machines.
//
// The registry (spec vault-sync "Derive the registry from the descriptors"):
// every installation of Coffer that has converged with this remote, as a derived
// view of `machines/*.yaml` rather than a synced table.
//
// "Last seen" is when that machine last ran a round against the remote, read
// from the descriptor it pushed — so a machine that has been off for a week
// says so here without anyone having to retire it first.
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useMachines } from "@/lib/hooks/useMachines";
import { SyncMachineRow } from "./SyncMachineRow";

const COLUMNS = [
  "name",
  "system",
  "lastSeen",
  "lastRound",
  "version",
  "key",
  "agents",
  "actions",
] as const;

export function SyncMachinesTab() {
  const { t } = useTranslation();
  const { data, isPending } = useMachines();
  const machines = data?.machines ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sync.machines.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("sync.machines.description")}</p>

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
      </CardContent>
    </Card>
  );
}
