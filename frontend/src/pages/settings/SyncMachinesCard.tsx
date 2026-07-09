// frontend/src/pages/settings/SyncMachinesCard.tsx
//
// Settings → Sync → Machines (spec 010 machine identity, ADR-043). Lists every
// machine known to the vault from the workspace registry; the local machine is
// badged and its display name is editable in place (committed on blur/Enter,
// mirroring the sync config fields). Other machines' entries update as they
// sync.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import { useRenameMachine, useSyncMachines, type SyncMachine } from "@/lib/hooks/useSync";

function MachineRow({ machine }: { machine: SyncMachine }) {
  const { t } = useTranslation();
  const rename = useRenameMachine();
  const [name, setName] = useState(machine.display_name);

  useEffect(() => {
    setName(machine.display_name);
  }, [machine.display_name]);

  const commit = () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === machine.display_name) {
      setName(machine.display_name);
      return;
    }
    rename.mutate(trimmed);
  };

  const meta = [machine.platform, machine.os_version].filter(Boolean).join(" ");
  const lastSync = machine.last_sync_at
    ? `${t("settings.sync.lastSync")}: ${new Date(machine.last_sync_at).toLocaleString()}`
    : t("settings.sync.neverSynced");

  return (
    <div className="flex items-center justify-between gap-3 rounded-md border p-3">
      <div className="min-w-0 flex-1">
        {machine.is_local ? (
          <Input
            aria-label={t("settings.sync.machineName")}
            value={name}
            disabled={rename.isPending}
            onChange={(e) => setName(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
            className="h-8 max-w-xs font-medium"
          />
        ) : (
          <p className="truncate text-sm font-medium">{machine.display_name}</p>
        )}
        <p className="mt-1 text-xs text-foreground/50">
          {meta && <span className="mr-2">{meta}</span>}
          {lastSync}
        </p>
        {machine.is_local && rename.error && (
          <p className="mt-1 text-xs text-red-600">{translateApiError(t, rename.error)}</p>
        )}
      </div>
      {machine.is_local && <Badge variant="secondary">{t("settings.sync.thisMachine")}</Badge>}
    </div>
  );
}

export function SyncMachinesCard() {
  const { t } = useTranslation();
  const { data } = useSyncMachines();
  const machines = data?.machines ?? [];

  if (machines.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.sync.machines")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-foreground/70">{t("settings.sync.machinesHint")}</p>
        {machines.map((m) => (
          <MachineRow key={m.machine_id} machine={m} />
        ))}
      </CardContent>
    </Card>
  );
}
