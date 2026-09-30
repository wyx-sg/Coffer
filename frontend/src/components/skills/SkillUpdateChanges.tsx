// src/components/skills/SkillUpdateChanges.tsx
// The files an update changes, each with its operation and line counts, beside the selected file's diff.
import { useTranslation } from "react-i18next";

import { LineCounts } from "@/components/change-preview/LineCounts";
import { OpChip } from "@/components/change-preview/OpChip";
import type { SkillFileChange } from "@/lib/api/skills";
import { cn } from "@/lib/utils";
import { CHANGE_OP } from "./skillSourceHelpers";
import { SkillUpdateDiff } from "./SkillUpdateDiff";

interface Props {
  changes: SkillFileChange[];
  selected: string | null;
  onSelect: (path: string) => void;
  /** Heading over the list, e.g. "Changes · 2". */
  label: string;
}

export function SkillUpdateChanges({ changes, selected, onSelect, label }: Props) {
  const { t } = useTranslation();
  const current = changes.find((c) => c.path === selected) ?? changes[0];
  if (changes.length === 0) {
    return <p className="text-xs text-text-muted">{t("skillSources.update.noChanges")}</p>;
  }
  return (
    <div className="grid min-h-0 grid-cols-[240px_minmax(0,1fr)] gap-4">
      <div className="flex min-w-0 flex-col gap-1.5">
        <span className="text-2xs font-semibold text-text-muted">{label}</span>
        <ul className="flex flex-col gap-0.5" aria-label={label}>
          {changes.map((change) => {
            const on = change.path === current?.path;
            return (
              <li key={change.path}>
                <button
                  type="button"
                  aria-current={on ? "true" : undefined}
                  onClick={() => onSelect(change.path)}
                  className={cn(
                    "flex w-full min-w-0 items-center gap-2 rounded-item px-2 py-1.5 text-left",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
                    on ? "bg-surface-selected" : "hover:bg-surface-hover",
                  )}
                >
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-text">
                    {change.path}
                  </span>
                  <LineCounts added={change.additions} removed={change.deletions} />
                  <OpChip op={CHANGE_OP[change.status]} size="sm" />
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="min-w-0 overflow-y-auto">
        {current ? <SkillUpdateDiff change={current} /> : null}
      </div>
    </div>
  );
}
