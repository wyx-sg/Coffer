// frontend/src/pages/settings/SyncSettings.tsx
//
// Settings → Sync (spec 010). Configure the git remote you own, toggle
// auto-sync, run a sync, resolve conflicts, and bootstrap the master key onto a
// new machine. The key is transferred via a local file path (out-of-band) — it
// never travels through the sync repo.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusBadge, type StatusTone } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import {
  useResolveSync,
  useRunSync,
  useSyncConfig,
  useSyncStatus,
  useUpdateSyncConfig,
} from "@/lib/hooks/useSync";

import { SyncMasterKeyCard } from "./SyncMasterKeyCard";

const SYNC_TONE: Record<string, StatusTone> = {
  clean: "success",
  conflicted: "warning",
  credentials_locked: "warning",
  error: "danger",
  syncing: "info",
  unconfigured: "neutral",
};

export function SyncSettings() {
  const { t } = useTranslation();
  const { data: config, isPending } = useSyncConfig();
  const { data: status } = useSyncStatus();
  const update = useUpdateSyncConfig();
  const run = useRunSync();
  const resolve = useResolveSync();
  const [remote, setRemote] = useState("");
  const [branch, setBranch] = useState("main");
  const [enabled, setEnabled] = useState(false);
  const [auto, setAuto] = useState(false);
  const [interval, setIntervalSeconds] = useState(300);

  useEffect(() => {
    if (!config) return;
    setRemote(config.remote ?? "");
    setBranch(config.branch);
    setEnabled(config.enabled);
    setAuto(config.auto);
    setIntervalSeconds(config.interval_seconds);
  }, [config]);

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-foreground/60">{t("common.loading")}</CardContent>
      </Card>
    );
  }

  const save = () =>
    update.mutate({ remote: remote || null, branch, enabled, auto, interval_seconds: interval });

  const syncTone: StatusTone = status ? (SYNC_TONE[status.status] ?? "neutral") : "neutral";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.sync.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-foreground/70">{t("settings.sync.description")}</p>

          {status && (
            <div className="rounded-md border p-3 text-sm">
              <span className="text-foreground/60">{t("settings.sync.status")}: </span>
              <span role="status">
                <StatusBadge
                  tone={syncTone}
                  label={t(`settings.sync.statuses.${status.status}`)}
                  pulse={status.status === "syncing"}
                />
              </span>
              {status.last_sync_at && (
                <span className="ml-2 text-foreground/50">
                  {t("settings.sync.lastSync")}: {new Date(status.last_sync_at).toLocaleString()}
                </span>
              )}
              {status.locked_refs.length > 0 && (
                <p className="mt-1 text-amber-600">
                  {t("settings.sync.lockedHint", { refs: status.locked_refs.join(", ") })}
                </p>
              )}
              {status.last_error && <p className="mt-1 text-red-600">{status.last_error}</p>}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="sync-remote">{t("settings.sync.remote")}</Label>
            <Input
              id="sync-remote"
              value={remote}
              placeholder="git@github.com:you/coffer-vault.git"
              onChange={(e) => setRemote(e.target.value)}
            />
          </div>
          {/* Branch is an internal ref name in Coffer's own sync vault repo, not
              the user's project branch; both machines default to "main", so it is
              not user-facing. We still round-trip the loaded value on save to
              preserve a non-default branch set via the CLI (`coffer sync --branch`). */}
          <div className="flex items-center justify-between">
            <Label htmlFor="sync-enabled">{t("settings.sync.enable")}</Label>
            <Switch id="sync-enabled" checked={enabled} onCheckedChange={setEnabled} />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="sync-auto">{t("settings.sync.auto")}</Label>
            <Switch id="sync-auto" checked={auto} onCheckedChange={setAuto} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sync-interval">{t("settings.sync.interval")}</Label>
            <Input
              id="sync-interval"
              type="number"
              value={interval}
              onChange={(e) => setIntervalSeconds(Number(e.target.value))}
            />
          </div>
          {update.error && (
            <p className="text-sm text-red-600">{translateApiError(t, update.error)}</p>
          )}
          <div className="flex gap-2">
            <Button onClick={save} disabled={update.isPending}>
              {t("common.save")}
            </Button>
            <Button variant="secondary" onClick={() => run.mutate()} disabled={run.isPending}>
              {t("settings.sync.syncNow")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {status?.status === "conflicted" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("settings.sync.conflicts")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <ul className="list-disc pl-5 text-sm text-foreground/70">
              {status.conflict_paths.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                onClick={() => resolve.mutate({ strategy: "ours", paths: [] })}
              >
                {t("settings.sync.resolveOurs")}
              </Button>
              <Button
                variant="secondary"
                onClick={() => resolve.mutate({ strategy: "theirs", paths: [] })}
              >
                {t("settings.sync.resolveTheirs")}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <SyncMasterKeyCard />
    </div>
  );
}
