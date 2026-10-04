// frontend/src/pages/sync/SyncMachinesTab.tsx — Sync › Machines (board 6.4.24).
//
// The registry (spec vault-sync "Derive the registry from the descriptors"):
// every Mac that has converged with this remote, as a derived view of
// `machines/*.yaml` rather than a synced table — so it cannot conflict.
//
// "Last seen" is when that machine last ran a round against the remote, read
// from the descriptor it pushed — so a Mac that has been off for a month says
// so here without anyone having to retire it first.
//
// Retire runs at once and the toast offers Undo (6.4.26): the registry entry
// is all it removes, so the mistake it can make is cheap to take back.
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { Machine } from "@/lib/api/sync";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useMachines, useRestoreMachine, useRetireMachine } from "@/lib/hooks/useMachines";
import { SyncMachineRow } from "./SyncMachineRow";

const COLUMNS = ["icon", "name", "lastSeen", "lastRound", "version", "agents", "actions"] as const;

export function SyncMachinesTab() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data, isPending } = useMachines();
  const retire = useRetireMachine();
  const restore = useRestoreMachine();
  const machines = data?.machines ?? [];
  const now = new Date();

  const onRetire = (machine: Machine) =>
    retire.mutate(machine.machine_id, {
      onSuccess: () =>
        toast.info(t("sync.machines.retired", { name: machine.name }), {
          undo: () =>
            restore.mutate(machine.machine_id, {
              onError: (error) => toast.error(translateApiError(t, error)),
            }),
        }),
      onError: (error) => toast.error(translateApiError(t, error)),
    });

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
        <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
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
                  now={now}
                  onRetire={onRetire}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
