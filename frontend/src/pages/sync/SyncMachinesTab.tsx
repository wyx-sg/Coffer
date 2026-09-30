// frontend/src/pages/sync/SyncMachinesTab.tsx — Sync › Machines (board 6.5.20).
//
// The registry (spec vault-sync "Derive the registry from the descriptors"):
// every Mac that has converged with this remote, as a derived view of
// `machines/*.yaml` rather than a synced table — so it cannot conflict.
//
// "Last seen" is when that machine last ran a round against the remote, read
// from the descriptor it pushed — so a Mac that has been off for a month says
// so here without anyone having to retire it first. The Mac that curates
// knowledge for the whole vault carries a read-only "Runs curation" tag; the
// owner is chosen in Knowledge, not here.
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useInternalEngineConfig } from "@/lib/hooks/useInternalEngine";
import { useMachines } from "@/lib/hooks/useMachines";
import { SyncMachineRow } from "./SyncMachineRow";

const COLUMNS = ["icon", "name", "lastSeen", "lastRound", "version", "agents", "actions"] as const;

export function SyncMachinesTab() {
  const { t } = useTranslation();
  const { data, isPending } = useMachines();
  const engine = useInternalEngineConfig();
  const curator = engine.data?.curate_owner_machine_id ?? null;
  const machines = data?.machines ?? [];
  const now = new Date();

  return (
    <div className="flex flex-col gap-3" data-testid="sync-machines">
      <p className="text-sm text-text-muted">{t("sync.machines.description")}</p>
      {isPending ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : machines.length === 0 ? (
        <EmptyState title={t("sync.machines.empty")} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              {COLUMNS.map((column) => (
                <TableHead key={column} className={column === "icon" ? "w-8" : undefined}>
                  {column === "icon" || column === "actions" ? (
                    <span className="sr-only">{t(`sync.machines.columns.${column}`)}</span>
                  ) : (
                    t(`sync.machines.columns.${column}`)
                  )}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {machines.map((machine) => (
              <SyncMachineRow
                key={machine.machine_id}
                machine={machine}
                curates={curator !== null && machine.machine_id === curator}
                now={now}
              />
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
