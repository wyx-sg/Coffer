// frontend/src/pages/sync/SyncMachineRow.tsx — one row of the machine registry.
//
// Beside the name: "This Mac" on the local row, and a warning tag only
// when that Mac publishes a different master key — its secrets cannot be
// decrypted here. Unknown ("no fingerprint yet") is not a mismatch and shows
// nothing.
//
// The "More" menu offers Rename on this Mac's row only — a machine writes its
// own descriptor and no other machine's — and Retire on every other row, which
// retires at once (the tab's toast carries Undo).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Laptop, Monitor } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Badge } from "@/components/ui/badge";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { TableCell, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { Machine } from "@/lib/api/sync";
import { cn } from "@/lib/utils";
import { RenameMachineDialog } from "./SyncMachineDialogs";
import { isStale, lastSeenLabel, roundTime } from "./syncMachineTimes";
import { statusLabel } from "./syncRoundStatus";

function Tagged({
  label,
  tip,
  variant,
}: {
  label: string;
  tip: string;
  variant: "secondary" | "warning";
}) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge variant={variant} aria-label={`${label}: ${tip}`}>
            {label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{tip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

interface Props {
  machine: Machine;
  now: Date;
  /** Retire this machine now; the tab's toast offers Undo. */
  onRetire: (machine: Machine) => void;
}

export function SyncMachineRow({ machine, now, onRetire }: Props) {
  const { t, i18n } = useTranslation();
  const [renaming, setRenaming] = useState(false);
  const Icon = /book/i.test(`${machine.name} ${machine.hostname}`) ? Laptop : Monitor;

  const actions: MenuAction[] = machine.is_self
    ? [
        {
          key: "rename",
          label: t("sync.machines.rename"),
          onSelect: () => setRenaming(true),
        },
      ]
    : [
        {
          key: "retire",
          label: t("sync.machines.retire"),
          destructive: true,
          onSelect: () => onRetire(machine),
        },
      ];

  return (
    <TableRow data-testid={`machine-${machine.machine_id}`}>
      <TableCell className="w-8 text-text-muted">
        <Icon className="size-4" aria-hidden />
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-text" title={machine.machine_id}>
            {machine.name}
          </span>
          {machine.is_self ? <Badge variant="secondary">{t("sync.machines.thisMac")}</Badge> : null}
          {machine.key_matches === false ? (
            <Tagged
              variant="warning"
              label={t("sync.machines.keyDiffers")}
              tip={t("sync.machines.keyDiffersTip")}
            />
          ) : null}
        </div>
      </TableCell>
      <TableCell
        className={cn(
          "text-sm",
          isStale(machine.last_round_at, now) ? "text-warning" : "text-text-muted",
        )}
      >
        {lastSeenLabel(machine.last_round_at, now, t, i18n.language)}
      </TableCell>
      <TableCell className="text-sm text-text-muted">
        {machine.last_round_at && machine.last_round
          ? `${roundTime(machine.last_round_at, now, i18n.language)} · ${statusLabel(t, machine.last_round)}`
          : "—"}
      </TableCell>
      <TableCell className="font-mono text-xs text-text-muted">{machine.coffer_version}</TableCell>
      <TableCell>
        {machine.agents.length > 0 ? (
          <div className="flex items-center gap-1">
            {machine.agents.map((agent) => (
              <AgentBadge key={`${agent.type}:${agent.name}`} type={agent.type} size="sm" />
            ))}
          </div>
        ) : (
          <span className="text-text-subtle">—</span>
        )}
      </TableCell>
      <TableCell className="w-10 text-right">
        <ActionMenu label={t("sync.machines.more", { name: machine.name })} actions={actions} />
        {renaming ? (
          <RenameMachineDialog machine={machine} onClose={() => setRenaming(false)} />
        ) : null}
      </TableCell>
    </TableRow>
  );
}
