// src/components/skills/SkillAddSourceFields.tsx
// The three source forms of the Add skill dialog: a folder path, an archive file, a Git repository.
//
// Each form only collects its source and says when to look at it; the dialog
// owns the stage (spec skill-manager "Add skills from an archive": nothing is
// written until the user confirms, and a stage is cancelled whenever the source
// changes).
import { useRef } from "react";
import { FileArchive } from "lucide-react";
import { useTranslation } from "react-i18next";

import { FolderPickerField } from "@/components/FolderPickerField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatBytes } from "@/lib/utils";
import { ARCHIVE_ACCEPT, cleanPath, isJump } from "./skillSourceHelpers";

interface FolderProps {
  value: string;
  onChange: (value: string) => void;
  /** Look at the folder now (after a paste, a pick, or leaving the field). */
  onLook: (path: string) => void;
}

export function SkillAddFolderField({ value, onChange, onLook }: FolderProps) {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-col gap-1.5"
      onBlur={(e) => {
        // Moving to the Browse button is not leaving the field.
        if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
        const path = cleanPath(value);
        if (path) onLook(path);
      }}
    >
      <Label htmlFor="skill-add-folder" required>
        {t("skillSources.folder.label")}
      </Label>
      <FolderPickerField
        inputId="skill-add-folder"
        ariaLabel={t("skillSources.folder.label")}
        value={value || null}
        onChange={(next) => {
          const text = next ?? "";
          onChange(text);
          const path = cleanPath(text);
          if (path && isJump(value, text)) onLook(path);
        }}
        placeholder={t("skillSources.folder.placeholder")}
        typeable
      />
      <p className="text-xs text-text-muted">{t("skillSources.folder.help")}</p>
    </div>
  );
}

interface ArchiveProps {
  file: File | null;
  onPick: (file: File) => void;
}

export function SkillAddArchiveField({ file, onPick }: ArchiveProps) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const ext = file ? (/\.[^.]+$/.exec(file.name)?.[0] ?? "") : "";
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="skill-add-archive" required>
        {t("skillSources.archive.label")}
      </Label>
      <input
        id="skill-add-archive"
        ref={input}
        type="file"
        accept={ARCHIVE_ACCEPT}
        className="sr-only"
        onChange={(e) => {
          const picked = e.target.files?.[0];
          // Clear the input so choosing the same file again still reports a change.
          e.target.value = "";
          if (picked) onPick(picked);
        }}
      />
      <div className="flex min-h-[58px] items-center gap-2.5 rounded-lg border border-dashed border-border bg-surface-sunken px-3 py-2 text-text-muted">
        <FileArchive aria-hidden className="size-[15px] shrink-0" />
        <span className="flex min-w-0 flex-col gap-px">
          {file ? (
            <>
              <span className="truncate font-mono text-xs text-text">{file.name}</span>
              <span className="text-2xs text-text-muted">
                {t("skillSources.archive.meta", { ext, size: formatBytes(file.size) })}
              </span>
            </>
          ) : (
            <span className="text-xs">{t("skillSources.archive.empty")}</span>
          )}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="ml-auto"
          onClick={() => input.current?.click()}
        >
          {t("skillSources.archive.choose")}
        </Button>
      </div>
    </div>
  );
}

export interface GitLocation {
  url: string;
  ref: string;
  path: string;
}

interface GitProps {
  value: GitLocation;
  onChange: (value: GitLocation) => void;
  disabled?: boolean;
}

function GitInput({
  id,
  label,
  required,
  help,
  placeholder,
  value,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  required?: boolean;
  help?: string;
  placeholder: string;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} required={required}>
        {label}
      </Label>
      <Input
        id={id}
        className="font-mono text-xs"
        value={value}
        disabled={disabled}
        spellCheck={false}
        autoComplete="off"
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      {help ? <p className="text-xs text-text-muted">{help}</p> : null}
    </div>
  );
}

export function SkillAddGitFields({ value, onChange, disabled }: GitProps) {
  const { t } = useTranslation();
  return (
    <>
      <GitInput
        id="skill-add-git-url"
        label={t("skillSources.git.url")}
        required
        help={t("skillSources.git.urlHelp")}
        placeholder={t("skillSources.git.urlPlaceholder")}
        value={value.url}
        disabled={disabled}
        onChange={(url) => onChange({ ...value, url })}
      />
      <GitInput
        id="skill-add-git-ref"
        label={t("skillSources.git.ref")}
        placeholder={t("skillSources.git.refPlaceholder")}
        value={value.ref}
        disabled={disabled}
        onChange={(ref) => onChange({ ...value, ref })}
      />
      <GitInput
        id="skill-add-git-path"
        label={t("skillSources.git.path")}
        placeholder={t("skillSources.git.pathPlaceholder")}
        value={value.path}
        disabled={disabled}
        onChange={(path) => onChange({ ...value, path })}
      />
    </>
  );
}
