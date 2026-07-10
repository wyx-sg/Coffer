// frontend/src/pages/settings/SyncSettings.tsx
//
// Settings → Sync (spec 010). Configure the git remote you own, toggle
// auto-sync, run a sync, resolve conflicts, and bootstrap the master key onto a
// new machine. The key is transferred via a local file path (out-of-band) — it
// never travels through the sync repo.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import { useRunSync, useSyncConfig, useSyncStatus, useUpdateSyncConfig } from "@/lib/hooks/useSync";

import { SyncMachinesCard } from "./SyncMachinesCard";
import { SyncMasterKeyCard } from "./SyncMasterKeyCard";
import { SyncStatusLine } from "./SyncStatusLine";

export function SyncSettings() {
  const { t } = useTranslation();
  const { data: config, isPending } = useSyncConfig();
  const { data: status } = useSyncStatus();
  const update = useUpdateSyncConfig();
  const run = useRunSync();
  const [remote, setRemote] = useState("");
  const [branch, setBranch] = useState("main");
  const [pollRemote, setPollRemote] = useState(15);
  const [enabled, setEnabled] = useState(false);
  const [auto, setAuto] = useState(false);
  const [interval, setIntervalSeconds] = useState(300);

  useEffect(() => {
    if (!config) return;
    setRemote(config.remote ?? "");
    setBranch(config.branch);
    setPollRemote(config.poll_remote_seconds);
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

  // Auto-save: persist the whole config with the just-changed field overridden.
  // Switches pass their new value through `override` (state updates are async,
  // so we can't read the new value back from state synchronously); text/number
  // fields commit on blur via the change-guarded helpers below.
  const persist = (override: Partial<Parameters<typeof update.mutate>[0]>) =>
    update.mutate({
      remote: remote || null,
      branch,
      enabled,
      auto,
      interval_seconds: interval,
      poll_remote_seconds: pollRemote,
      ...override,
    });

  const commitRemote = () => {
    if ((remote || null) !== (config?.remote ?? null)) persist({ remote: remote || null });
  };
  const commitInterval = () => {
    if (interval !== config?.interval_seconds) persist({ interval_seconds: interval });
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.sync.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-foreground/70">{t("settings.sync.description")}</p>

          {status && <SyncStatusLine status={status} />}

          <div className="space-y-2">
            <Label htmlFor="sync-remote">{t("settings.sync.remote")}</Label>
            <Input
              id="sync-remote"
              value={remote}
              placeholder="git@github.com:you/coffer-vault.git"
              disabled={update.isPending}
              onChange={(e) => setRemote(e.target.value)}
              onBlur={commitRemote}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
              }}
            />
          </div>
          {/* Branch is an internal ref name in Coffer's own sync vault repo, not
              the user's project branch; both machines default to "main", so it is
              not user-facing. We still round-trip the loaded value on save to
              preserve a non-default branch set via the CLI (`coffer sync --branch`). */}
          <div className="flex items-center justify-between">
            <Label htmlFor="sync-enabled">{t("settings.sync.enable")}</Label>
            <Switch
              id="sync-enabled"
              checked={enabled}
              disabled={update.isPending}
              onCheckedChange={(v) => {
                setEnabled(v);
                persist({ enabled: v });
              }}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="sync-auto">{t("settings.sync.auto")}</Label>
            <Switch
              id="sync-auto"
              checked={auto}
              disabled={update.isPending}
              onCheckedChange={(v) => {
                setAuto(v);
                persist({ auto: v });
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sync-interval">{t("settings.sync.interval")}</Label>
            <Input
              id="sync-interval"
              type="number"
              value={interval}
              disabled={update.isPending}
              onChange={(e) => setIntervalSeconds(Number(e.target.value))}
              onBlur={commitInterval}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
              }}
            />
          </div>
          {update.error && (
            <p className="text-sm text-red-600">{translateApiError(t, update.error)}</p>
          )}
          {run.error && <p className="text-sm text-red-600">{translateApiError(t, run.error)}</p>}
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => run.mutate()} disabled={run.isPending}>
              {t("settings.sync.syncNow")}
            </Button>
          </div>
        </CardContent>
      </Card>

      <SyncMachinesCard />

      <SyncMasterKeyCard />
    </div>
  );
}
