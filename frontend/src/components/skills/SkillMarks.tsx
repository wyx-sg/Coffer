// frontend/src/components/skills/SkillMarks.tsx
// The small marks a skill wears beside its name, in the library and the
// detail header alike:
//
// - **Built-in** — Coffer's own generated skill sits in the same library as the
//   user's, so the list has to say which one the daemon rewrites at every
//   start. Informational, not a warning: nothing is wrong with it, it is simply
//   not the reader's to edit or delete, so it wears the muted tone.
// - **Copied** — a delivery fell back to a copy ("Fall back to copying where
//   links are unavailable"): that agent will not see edits to the master until
//   it is delivered again, so it wears the warning tone.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { toneClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

function Mark({
  testId,
  label,
  tip,
  tone,
}: {
  testId: string;
  label: string;
  tip: string;
  tone: "muted" | "warn";
}) {
  return (
    <Tooltip>
      {/* The span is the trigger, not the Badge: Badge is a plain function
          component, so Radix has nothing to anchor the tooltip to. `tabIndex`
          keeps the hint reachable from the keyboard. */}
      <TooltipTrigger asChild>
        <span tabIndex={0} className="inline-flex shrink-0 rounded-full">
          <Badge
            variant="outline"
            data-testid={testId}
            className={cn("cursor-default border-transparent font-sans", toneClass(tone))}
          >
            {label}
          </Badge>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{tip}</TooltipContent>
    </Tooltip>
  );
}

export function BuiltinMark() {
  const { t } = useTranslation();
  return (
    <Mark
      testId="skill-builtin-badge"
      label={t("skills.builtinBadge")}
      tip={t("skills.builtinTooltip")}
      tone="muted"
    />
  );
}

export function CopiedMark() {
  const { t } = useTranslation();
  return (
    <Mark
      testId="skill-degraded-badge"
      label={t("skills.degradedBadge")}
      tip={t("skills.degradedTooltip")}
      tone="warn"
    />
  );
}
