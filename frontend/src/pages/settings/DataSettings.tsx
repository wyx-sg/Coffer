// frontend/src/pages/settings/DataSettings.tsx
//
// Settings → Data (design 6.2.07–6.2.10; spec web-ui "Group the Data tab by
// what kind of data it is"): what Coffer keeps, where it lives and for how
// long, in four blocks — Vault (synced: size, versions, Open folder), Local
// content (not synced, the user backs it up: chat and channel attachments),
// History (the records, their retention, Clear expired now) and Rebuildable
// cache (the memory tree and transcript summary cache, one confirmed Clear).
// No "This Mac only" block. Sizes come from GET /api/v1/storage; folders open
// through the daemon's /fs routes. Every edit auto-saves.
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { CacheBlock } from "@/components/settings/storage/CacheBlock";
import { DataBlock } from "@/components/settings/storage/DataBlock";
import { HistoryBlock } from "@/components/settings/storage/HistoryBlock";
import { SettingRow } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath } from "@/lib/agents/display";
import { fsApi } from "@/lib/api/fs";
import { translateApiError } from "@/lib/api/errors";
import { useStorageSummary } from "@/lib/hooks/useStorage";
import { formatBytes } from "@/lib/utils";

function Location({ path }: { path: string }) {
  return <span className="font-mono text-xs text-text-muted">{abbreviateHomePath(path)}</span>;
}

export function DataSettings() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const storage = useStorageSummary();
  const data = storage.data;

  const open = (path: string, reveal = false) => {
    (reveal ? fsApi.reveal(path) : fsApi.open(path)).catch((err: unknown) =>
      toast.error(translateApiError(t, err)),
    );
  };
  const openButton = (path: string | undefined) => (
    <Button size="sm" variant="outline" disabled={!path} onClick={() => path && open(path)}>
      <FolderOpen aria-hidden /> {t("settings.data.openFolder")}
    </Button>
  );

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
      <p className="text-sm text-text-muted">{t("settings.data.intro")}</p>
      {storage.error ? (
        <p className="text-xs text-danger" role="alert">
          {translateApiError(t, storage.error)}
        </p>
      ) : null}
      <div className="flex flex-col gap-7">
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
        >
          {data ? (
            <SettingRow label={t("settings.data.location")}>
              <Location path={data.vault.path} />
            </SettingRow>
          ) : null}
        </DataBlock>

        <DataBlock
          title={t("settings.data.local.title")}
          size={storage.error ? "—" : data ? formatBytes(data.local_content.bytes) : null}
          description={t("settings.data.local.description")}
          action={openButton(data?.local_content.folder)}
          testId="settings-data-local"
        >
          {data ? (
            <>
              <SettingRow
                label={t("settings.data.local.attachments")}
                description={t("settings.data.local.attachmentsHelp")}
              >
                <span className="text-sm text-text" data-visual-volatile>
                  {formatBytes(data.local_content.bytes)}
                </span>
              </SettingRow>
              <SettingRow label={t("settings.data.location")}>
                <div className="flex flex-col items-end gap-0.5">
                  {data.local_content.locations.map((p) => (
                    <Location key={p} path={p} />
                  ))}
                </div>
              </SettingRow>
            </>
          ) : null}
        </DataBlock>

        <HistoryBlock
          size={storage.error ? "—" : data ? formatBytes(data.history.bytes) : null}
          onReveal={data?.history.path ? () => open(data.history.path, true) : undefined}
        />

        <CacheBlock bytes={storage.error ? 0 : (data?.cache.bytes ?? null)} />
      </div>
    </div>
  );
}
