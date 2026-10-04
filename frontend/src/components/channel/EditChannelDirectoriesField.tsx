// frontend/src/components/channel/EditChannelDirectoriesField.tsx
// The Working directories section of a channel's Settings tab — spec channels
// "Choose the working directory from chat": one list of folders, which /dir may
// switch a chat into (each also admits the folders under it; with none, /dir is
// off), and one of which may be the Default new conversations start in (with
// none marked, Coffer's workspace). Rows carry Set as default and a remove ✕; a long
// list scrolls inside its box instead of growing the page.
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { FolderPicker } from "@/components/FolderPicker";
import { SettingRow } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
import { DIRECTORIES_MAX, normaliseDirectory } from "@/lib/channels/editChannel";

interface Props {
  directories: string[];
  /** The listed folder new conversations start in; null is Coffer's workspace. */
  defaultDirectory: string | null;
  onChange: (directories: string[], defaultDirectory: string | null) => void;
}

export function EditChannelDirectoriesField({ directories, defaultDirectory, onChange }: Props) {
  const { t } = useTranslation();

  const add = (path: string) => {
    const next = normaliseDirectory(path);
    if (next === null || directories.includes(next)) return;
    onChange([...directories, next], defaultDirectory);
  };
  const remove = (path: string) =>
    onChange(
      directories.filter((d) => d !== path),
      path === defaultDirectory ? null : defaultDirectory,
    );

  return (
    <SettingRow layout="stack" label={t("channels.edit.directories.list")}>
      <div className="flex w-full flex-col items-start gap-2">
        {directories.length > 0 ? (
          <ul
            aria-label={t("channels.edit.directories.list")}
            className="max-h-64 w-full divide-y divide-border-subtle overflow-y-auto rounded-lg border border-border-subtle"
          >
            {directories.map((path) => {
              const isDefault = path === defaultDirectory;
              return (
                <li key={path} className="flex items-center gap-2 px-3 py-1.5">
                  <span className="min-w-0 truncate font-mono text-xs" title={path}>
                    {path}
                  </span>
                  {isDefault ? (
                    <span className="shrink-0 text-xs text-text-muted">
                      {t("channels.edit.directories.defaultTag")}
                    </span>
                  ) : null}
                  <span className="ml-auto flex shrink-0 items-center">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={
                        isDefault
                          ? t("channels.edit.directories.unsetDefaultAria", { path })
                          : t("channels.edit.directories.setDefaultAria", { path })
                      }
                      onClick={() => onChange(directories, isDefault ? null : path)}
                    >
                      {isDefault
                        ? t("channels.edit.directories.unsetDefault")
                        : t("channels.edit.directories.setDefault")}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("channels.edit.directories.removeAria", { path })}
                      onClick={() => remove(path)}
                    >
                      <X aria-hidden />
                    </Button>
                  </span>
                </li>
              );
            })}
          </ul>
        ) : null}
        {directories.length < DIRECTORIES_MAX ? (
          <FolderPicker value={null} onChange={add} label={t("channels.edit.directories.add")} />
        ) : (
          <p className="text-xs text-text-muted">
            {t("channels.edit.directories.tooMany", { max: DIRECTORIES_MAX })}
          </p>
        )}
      </div>
    </SettingRow>
  );
}
