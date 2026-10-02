// frontend/src/components/channel/EditChannelDirectoriesField.tsx
// The Working directories section of a channel's Settings tab — spec channels
// "Choose the working directory from chat": the Default folder new
// conversations start in, and the folders /dir may switch a chat into (each
// also admits the folders under it; with none, /dir is off). The default is
// picked or typed; the allowed list is rows with Remove and an Add directory…
// button. A typed default that is not an absolute path shows an error and is
// never saved.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { FolderPicker } from "@/components/FolderPicker";
import { FolderPickerField } from "@/components/FolderPickerField";
import { SettingRow } from "@/components/settings/SettingsLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DIRECTORIES_MAX, normaliseDirectory } from "@/lib/channels/editChannel";

interface Props {
  /** The default folder as typed (blank = none). */
  defaultText: string;
  onDefaultChange: (text: string) => void;
  directories: string[];
  onDirectoriesChange: (directories: string[]) => void;
}

export function EditChannelDirectoriesField({
  defaultText,
  onDefaultChange,
  directories,
  onDirectoriesChange,
}: Props) {
  const { t } = useTranslation();
  const id = useId();
  const defaultId = `${id}-default`;
  const defaultInvalid = defaultText.trim() !== "" && normaliseDirectory(defaultText) === null;
  const defaultPath = normaliseDirectory(defaultText);

  const add = (path: string) => {
    const next = normaliseDirectory(path);
    if (next === null || directories.includes(next)) return;
    onDirectoriesChange([...directories, next]);
  };

  return (
    <>
      <SettingRow
        layout="stack"
        label={t("channels.edit.directories.default")}
        labelFor={defaultId}
        description={t("channels.edit.directories.defaultHint")}
        status={
          defaultInvalid ? (
            <p className="text-xs text-danger" role="alert">
              {t("channels.edit.directories.notAbsolute", { path: defaultText.trim() })}
            </p>
          ) : null
        }
      >
        <FolderPickerField
          inputId={defaultId}
          ariaLabel={t("channels.edit.directories.default")}
          value={defaultText || null}
          placeholder={t("channels.edit.directories.defaultPlaceholder")}
          onChange={(path) => onDefaultChange(path ?? "")}
          clearable
          typeable
        />
      </SettingRow>
      <SettingRow
        layout="stack"
        label={t("channels.edit.directories.allowed")}
        description={t("channels.edit.directories.allowedHint")}
      >
        <div className="flex w-full flex-col items-start gap-2">
          {directories.length > 0 ? (
            <ul className="w-full divide-y divide-border-subtle rounded-lg border border-border-subtle">
              {directories.map((path) => (
                <li key={path} className="flex items-center gap-2 px-3 py-2">
                  <span className="min-w-0 truncate font-mono text-xs" title={path}>
                    {path}
                  </span>
                  {path === defaultPath ? (
                    <Badge variant="secondary">{t("channels.edit.directories.defaultTag")}</Badge>
                  ) : null}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="ml-auto"
                    aria-label={t("channels.edit.directories.removeAria", { path })}
                    onClick={() => onDirectoriesChange(directories.filter((d) => d !== path))}
                  >
                    {t("channels.edit.directories.remove")}
                  </Button>
                </li>
              ))}
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
    </>
  );
}
