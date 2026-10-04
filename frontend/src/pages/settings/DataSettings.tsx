// frontend/src/pages/settings/DataSettings.tsx
//
// Settings → Data (canvas 1.4.11, 1.4.12; spec web-ui "Group the Data tab by
// what kind of data it is"): what Coffer keeps, where it lives and for how
// long, in four sections — Vault (the git repository at ~/.coffer/vault: size
// with .git, versions, Open folder), Local content (not synced, the user
// backs it up: chat and channel attachments with their retention row, Open folder),
// History (the records, their retention, Clear expired now) and Rebuildable
// cache (the memory tree and transcript summary cache, one confirmed Clear).
// No "This Mac only" block. Sizes come from GET /api/v1/storage; folders open
// through the daemon's /fs routes, and a folder button names its folder in a
// tooltip rather than in a row of its own. Every edit auto-saves.
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { LoadError } from "@/components/LoadError";
import { CacheBlock } from "@/components/settings/storage/CacheBlock";
import { DataBlock } from "@/components/settings/storage/DataBlock";
import { HistoryBlock } from "@/components/settings/storage/HistoryBlock";
import { RetentionPolicySection } from "@/components/settings/storage/RetentionPolicySection";
import { RetentionSaveFailed } from "@/components/settings/storage/RetentionSaveFailed";
import { SETTINGS_STACK, SettingsTabHeader } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useFsActions } from "@/lib/fsActions";
import { translateApiError } from "@/lib/api/errors";
import { useRetentionPolicies, useUpdateRetentionPolicy } from "@/lib/hooks/useRetention";
import { useStorageSummary } from "@/lib/hooks/useStorage";
import { formatBytes } from "@/lib/utils";

export function DataSettings() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const storage = useStorageSummary();
  const data = storage.data;
  const policies = useRetentionPolicies();
  const update = useUpdateRetentionPolicy();
  // Attachments are deleted by their own retention policy; its row sits in Local content.
  const attachments = policies.data?.policies.find((p) => p.table_name === "attachments");

  const open = (path: string, reveal = false) => {
    (reveal ? fs.reveal(path) : fs.open(path)).catch((err: unknown) =>
      toast.error(translateApiError(t, err)),
    );
  };
  const openButton = (path: string | undefined) => {
    const button = (
      <Button size="sm" variant="outline" disabled={!path} onClick={() => path && open(path)}>
        <FolderOpen aria-hidden /> {t("settings.data.openFolder")}
      </Button>
    );
    return path ? (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent className="font-mono">{abbreviateHomePath(path)}</TooltipContent>
      </Tooltip>
    ) : (
      button
    );
  };

  const vaultSize = data
    ? data.vault.versions === null || data.vault.versions === undefined
      ? formatBytes(data.vault.bytes)
      : t("settings.data.vault.size", {
          size: formatBytes(data.vault.bytes),
          count: data.vault.versions,
          versions: data.vault.versions.toLocaleString(),
        })
    : null;

  return (
    <div className="flex flex-col gap-5">
      <SettingsTabHeader title={t("settings.tabs.data")} intro={t("settings.data.intro")} />
      {storage.error ? (
        <LoadError error={storage.error} onRetry={() => void storage.refetch()} />
      ) : null}
      <div className={SETTINGS_STACK}>
        <RetentionSaveFailed update={update} />
        <DataBlock
          title={t("settings.data.vault.title")}
          size={storage.error ? "—" : vaultSize}
          description={
            data && data.vault.versions == null
              ? t("settings.data.vault.notRepository")
              : t("settings.data.vault.description")
          }
          action={openButton(data?.vault.path)}
          testId="settings-data-vault"
        />

        <DataBlock
          title={t("settings.data.local.title")}
          size={storage.error ? "—" : data ? formatBytes(data.local_content.bytes) : null}
          description={
            attachments && attachments.retention_days !== null
              ? t("settings.data.local.descriptionDays", { count: attachments.retention_days })
              : t("settings.data.local.description")
          }
          action={openButton(data?.local_content.folder)}
          testId="settings-data-local"
        >
          {attachments ? (
            <RetentionPolicySection
              policy={attachments}
              failed={update.isError && update.variables?.tableName === attachments.table_name}
              updating={update.isPending}
              onUpdate={(retentionDays) =>
                update.mutate({ tableName: attachments.table_name, retentionDays })
              }
            />
          ) : null}
        </DataBlock>

        <HistoryBlock
          size={storage.error ? "—" : data ? formatBytes(data.history.bytes) : null}
          path={data?.history.path}
          onReveal={data?.history.path ? () => open(data.history.path, true) : undefined}
          update={update}
        />

        <CacheBlock bytes={storage.error ? 0 : (data?.cache.bytes ?? null)} />
      </div>
    </div>
  );
}
