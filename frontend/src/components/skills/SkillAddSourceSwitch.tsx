// src/components/skills/SkillAddSourceSwitch.tsx
// The Add skill dialog's source switch: a segmented control on its own line — From a folder, From an archive, From Git.
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export type SkillAddSource = "folder" | "archive" | "git";

const SOURCES: readonly SkillAddSource[] = ["folder", "archive", "git"];

interface Props {
  value: SkillAddSource;
  onChange: (next: SkillAddSource) => void;
}

export function SkillAddSourceSwitch({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div
      role="radiogroup"
      aria-label={t("skillSources.add.sourceLabel")}
      className="inline-flex gap-0.5 self-start rounded-md border border-border-subtle bg-surface-sunken p-[3px]"
    >
      {SOURCES.map((source) => {
        const on = source === value;
        return (
          <button
            key={source}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => !on && onChange(source)}
            className={cn(
              "h-6 rounded-sm px-2.5 text-xs font-label transition-colors duration-fast",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
              on ? "bg-surface-raised text-text shadow-lifted" : "text-text-muted hover:text-text",
            )}
          >
            {t(`skillSources.add.source.${source}`)}
          </button>
        );
      })}
    </div>
  );
}
