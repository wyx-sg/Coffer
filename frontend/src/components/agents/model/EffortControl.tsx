// src/components/agents/model/EffortControl.tsx — the Effort segmented control: "Model default" plus only the levels the chosen model reports.
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

const KNOWN_LEVELS = ["minimal", "low", "medium", "high", "xhigh", "max"];
const DEFAULT = "__default__";

interface Props {
  /** The levels the chosen model reports, in the agent's own order. */
  levels: string[];
  /** The draft level; null = the model's own default. */
  value: string | null;
  onChange: (next: string | null) => void;
  /** Read-only: the binding cannot carry an effort (yet), or nothing writes it. */
  readOnly?: boolean;
  /** Grey the whole control out (it is not the agent's to set), not just lock it. */
  disabledLook?: boolean;
  /** The muted line under the control. */
  hint: string;
}

export function EffortControl({ levels, value, onChange, readOnly, disabledLook, hint }: Props) {
  const { t } = useTranslation();
  const label = (level: string) =>
    KNOWN_LEVELS.includes(level) ? t(`agents.modelTab.effort.levels.${level}`) : level;
  const options = [DEFAULT, ...levels];
  const current = value ?? DEFAULT;

  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", disabledLook && "opacity-60")}>
      <span className="text-xs font-label text-text">{t("agents.modelTab.effort.label")}</span>
      <div
        role="radiogroup"
        aria-label={t("agents.modelTab.effort.label")}
        aria-readonly={readOnly || undefined}
        aria-disabled={disabledLook || undefined}
        className="inline-flex flex-wrap gap-0.5 self-start rounded-md border border-border-subtle bg-surface-sunken p-[3px]"
      >
        {options.map((option) => {
          const checked = option === current;
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={checked}
              disabled={readOnly}
              onClick={() => onChange(option === DEFAULT ? null : option)}
              className={cn(
                "h-6 rounded-sm px-2.5 text-xs font-label outline-none transition-colors duration-fast focus-visible:ring-2 focus-visible:ring-focus-ring disabled:cursor-not-allowed",
                checked
                  ? "bg-surface-raised text-text shadow-lifted"
                  : "text-text-muted enabled:hover:text-text",
              )}
            >
              {option === DEFAULT ? t("agents.modelTab.effort.modelDefault") : label(option)}
            </button>
          );
        })}
      </div>
      <span className="text-xs text-text-subtle">{hint}</span>
    </div>
  );
}
