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
//   retire — says out loud that it also strips the machine from every scope
//           naming it, because that is a change to OTHER resources.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { TableCell, TableRow } from "@/components/ui/table";
import type { Machine } from "@/lib/api/sync";
import { useRenameSelf, useRetireMachine } from "@/lib/hooks/useMachines";

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
      <TableCell>{machine.os}</TableCell>
      <TableCell className="font-mono text-xs">{machine.hostname}</TableCell>
      <TableCell>{machine.coffer_version}</TableCell>
      <TableCell title={t("sync.machines.lastConvergedHint")}>
        {machine.last_converged_on ?? (
          <span className="text-muted-foreground">{t("sync.machines.never")}</span>
        )}
      </TableCell>
      <TableCell>
        <KeyCell matches={machine.key_matches} />
      </TableCell>
      <TableCell>
        {machine.agents.length > 0 ? (
          machine.agents.join(", ")
        ) : (
          <span className="text-muted-foreground">{t("sync.machines.noAgents")}</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        {machine.is_self ? null : (
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => setConfirming(true)}
          >
            <Trash2 className="mr-1.5 size-3.5" /> {t("sync.machines.retire")}
          </Button>
        )}
        <ConfirmDialog
          open={confirming}
          onOpenChange={setConfirming}
          title={t("sync.machines.retireTitle", { name: machine.name })}
          description={t("sync.machines.retireBody")}
          confirmLabel={t("sync.machines.retire")}
          pending={retire.isPending}
          onConfirm={() => {
            retire.mutate(machine.machine_id, { onSettled: () => setConfirming(false) });
          }}
        />
      </TableCell>
    </TableRow>
  );
}
