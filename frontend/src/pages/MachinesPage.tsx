// frontend/src/pages/MachinesPage.tsx — spec 010-sync machines fleet view
// (ADR-045). Lists every machine synced into this vault (byte-identical data
// to Settings → Sync → Machines, surfaced under its own top-level nav item —
// see backend/coffer/surfaces/http/machines_routes.py) plus a status strip
// that mirrors SyncStatusLine so the sync state is visible without a detour
// through Settings. Each card links to the machine's detail page (spec 010
// amendment, Task 18) — /machines/{id} 404s until that page lands.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Laptop } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { StatusBadge, type StatusTone } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import { useMachines, type SyncMachine } from "@/lib/hooks/useMachines";
import { useRenameMachine, useRunSync, useSyncStatus } from "@/lib/hooks/useSync";

// Mirrors SyncStatusLine's tone map (settings/SyncStatusLine.tsx) — kept
// local rather than shared since the two status strips render differently
// (this one is a compact single line with a run-now action).
const SYNC_TONE: Record<string, StatusTone> = {
  clean: "success",
  conflicted: "warning",
  credentials_locked: "warning",
  error: "danger",
  syncing: "info",
  unconfigured: "neutral",
};

function StatusStrip() {
  const { t } = useTranslation();
  const { data: status } = useSyncStatus();
  const run = useRunSync();

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-foreground/60">{t("machines.status")}:</span>
          {status ? (
            <span role="status">
              <StatusBadge
                tone={SYNC_TONE[status.status] ?? "neutral"}
                label={t(`settings.sync.statuses.${status.status}`)}
                pulse={status.status === "syncing"}
              />
            </span>
          ) : null}
          <span className="text-foreground/50">
            {status?.last_sync_at
              ? `${t("machines.lastSync")}: ${new Date(status.last_sync_at).toLocaleString()}`
              : t("machines.neverSynced")}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={() => run.mutate()} disabled={run.isPending}>
            {t("machines.runNow")}
          </Button>
          <Link to="/settings/sync" className="text-sm text-primary hover:underline">
            {t("machines.configureLink")}
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

// Adapted from settings/SyncMachinesCard.tsx's MachineRow — same in-place
// rename affordance for the local machine — plus a link to the detail page.
function MachineCard({ machine }: { machine: SyncMachine }) {
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
    ? `${t("machines.lastSync")}: ${new Date(machine.last_sync_at).toLocaleString()}`
    : t("machines.neverSynced");

  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
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
            {machine.is_local && <Badge variant="secondary">{t("machines.thisMachine")}</Badge>}
          </div>
          <p className="mt-1 text-xs text-foreground/50">
            {meta && <span className="mr-2">{meta}</span>}
            {lastSync}
          </p>
          {machine.is_local && rename.error && (
            <p className="mt-1 text-xs text-red-600">{translateApiError(t, rename.error)}</p>
          )}
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to={`/machines/${encodeURIComponent(machine.machine_id)}`}>
            {t("machines.viewSlice")}
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export function MachinesPage() {
  const { t } = useTranslation();
  const { data, isPending, error } = useMachines();
  const machines = data?.machines ?? [];

  return (
    <div className="space-y-6">
      <PageHeader icon={Laptop} title={t("machines.title")} subtitle={t("machines.subtitle")} />

      <StatusStrip />

      {isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">{t("machines.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : machines.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("machines.empty")}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {machines.map((m) => (
            <MachineCard key={m.machine_id} machine={m} />
          ))}
        </div>
      )}
    </div>
  );
}
