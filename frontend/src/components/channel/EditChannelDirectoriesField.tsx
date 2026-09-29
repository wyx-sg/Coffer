// frontend/src/components/channel/EditChannelDirectoriesField.tsx
// The /dir allow-list of the edit-channel form — spec channels "Choose the
// working directory from chat": the only folders a chat may switch its agent
// into, one absolute path per line. The draft is the raw text, so a relative
// line is shown as an error (and blocks Save) instead of being dropped.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DIRECTORIES_MAX, parseDirectories } from "./editChannel";

export function EditChannelDirectoriesField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const errorId = `${id}-error`;
  const { invalid, tooMany } = parseDirectories(value);
  const error =
    invalid.length > 0
      ? t("channels.edit.directories.notAbsolute", { path: invalid[0] })
      : tooMany
        ? t("channels.edit.directories.tooMany", { max: DIRECTORIES_MAX })
        : null;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-0.5">
        <Label htmlFor={id}>{t("channels.edit.directories.label")}</Label>
        <HelpTip>
          <p className="text-sm">{t("channels.edit.directories.help")}</p>
        </HelpTip>
      </div>
      <Textarea
        id={id}
        className="font-mono text-xs"
        placeholder={t("channels.edit.directories.placeholder")}
        spellCheck={false}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {error ? (
        <p id={errorId} className="text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
