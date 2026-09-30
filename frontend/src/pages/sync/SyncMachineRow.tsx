// frontend/src/pages/sync/SyncMachineRow.tsx — one row of the machine registry.
//
// Three cells carry more meaning than their width suggests:
//
//   name  — editable in place, but only on the local row: a machine writes its
//           own descriptor and no other machine's. The id's first 8 characters
//           sit under it so two machines the user called "laptop" are still
//           tellable apart, since the id is what `scope` actually references.
//   key   — a ✓/✗ rather than two fingerprints to compare by eye. ✗ means that
//           machine's credentials cannot be decrypted here; "—" means one side
//           has published no fingerprint yet, which is not a mismatch.
//   retire — removes only the machine's descriptor from the registry.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { TableCell, TableRow } from "@/components/ui/table";
import type { Machine } from "@/lib/api/sync";
import { useRenameSelf, useRetireMachine } from "@/lib/hooks/useMachines";
import { formatDateTime } from "@/lib/utils";
import { statusLabel } from "./syncRoundStatus";

function KeyCell({ matches }: { matches: boolean | null }) {
  const { t } = useTranslation();
  if (matches === null) {
    return (
      <span className="text-muted-foreground" title={t("sync.machines.keyUnknown")}>
        —
      </span>
    );
  }
  return matches ? (
    <span className="text-status-ok" title={t("sync.machines.keyMatches")}>
      ✓
    </span>
  ) : (
    <span className="text-status-err" title={t("sync.machines.keyDiffers")}>
      ✗ <span className="text-xs">{t("sync.machines.keyDiffers")}</span>
    </span>
  );
}

function NameCell({ machine }: { machine: Machine }) {
  const { t } = useTranslation();
  const rename = useRenameSelf();
  const [draft, setDraft] = useState(machine.name);

  const commit = () => {
    const next = draft.trim();
    if (!next || next === machine.name) {
      setDraft(machine.name);
      return;
    }
    rename.mutate(next);
  };

  return (
    <div className="space-y-1">
      {machine.is_self ? (
        <Input
          value={draft}
          aria-label={t("sync.machines.renameLabel")}
          disabled={rename.isPending}
          className="h-8 max-w-48"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
      ) : (
        <span className="font-medium">{machine.name}</span>
      )}
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground">
          {machine.machine_id.slice(0, 8)}
        </span>
        {machine.is_self ? (
          <Badge variant="secondary">{t("sync.machines.thisMachine")}</Badge>
        ) : null}
      </div>
    </div>
  );
}

export function SyncMachineRow({ machine }: { machine: Machine }) {
  const { t } = useTranslation();
  const retire = useRetireMachine();
  const [confirming, setConfirming] = useState(false);

  return (
    <TableRow data-testid={`machine-${machine.machine_id}`}>
      <TableCell>
        <NameCell machine={machine} />
      </TableCell>
      <TableCell>
        {machine.os}
        <span className="block font-mono text-xs text-muted-foreground">{machine.hostname}</span>
      </TableCell>
      <TableCell className="text-xs">
        {machine.last_round_at ? (
          formatDateTime(machine.last_round_at)
        ) : (
          <span className="text-muted-foreground">{t("sync.machines.never")}</span>
        )}
      </TableCell>
      <TableCell className="text-xs">
        {machine.last_round ? statusLabel(t, machine.last_round) : "—"}
      </TableCell>
      <TableCell>{machine.coffer_version}</TableCell>
      <TableCell>
        <KeyCell matches={machine.key_matches} />
      </TableCell>
      <TableCell className="text-xs">
        {machine.agents.length > 0 ? (
          <ul className="space-y-0.5">
            {machine.agents.map((agent) => (
              <li key={`${agent.type}:${agent.name}`}>
                {t("sync.machines.agent", { type: agent.type, count: agent.plugins.length })}
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-muted-foreground">{t("sync.machines.noAgents")}</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        {machine.is_self ? null : (
          <TableActionButton
            icon={Trash2}
            label={t("sync.machines.retire")}
            destructive
            onClick={() => setConfirming(true)}
          />
        )}
        <ConfirmDialog
          open={confirming}
          onOpenChange={(next) => {
            setConfirming(next);
            if (!next) retire.reset();
          }}
          title={t("sync.machines.retireTitle", { name: machine.name })}
          description={t("sync.machines.retireBody")}
          confirmLabel={t("sync.machines.retire")}
          pending={retire.isPending}
          error={retire.error}
          onConfirm={() => {
            // Closes only on success, so a refusal stays up with its reason.
            retire.mutate(machine.machine_id, { onSuccess: () => setConfirming(false) });
          }}
        />
      </TableCell>
    </TableRow>
  );
}
