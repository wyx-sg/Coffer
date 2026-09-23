// frontend/src/components/workflow/ActionGate.tsx
// A run records the machine that owns it, and only that machine's daemon may
// advance it. Everywhere else the run is visible and read-only.
//
// "Read-only" is rendered as disabled controls plus a tooltip that NAMES the
// machine: a disabled button with no explanation is indistinguishable from a
// broken one, and the name is the only thing that tells the developer where to
// go instead. A disabled button fires no pointer events, so the trigger is the
// wrapping span — the standard Radix workaround, kept in one place.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface Props {
  /** `RunOut.owned_here` — false when another machine advances this run. */
  ownedHere: boolean;
  /** Display name of the owning machine (falls back to its id). */
  machine: string;
  children: ReactNode;
}

export function ActionGate({ ownedHere, machine, children }: Props) {
  const { t } = useTranslation();
  if (ownedHere) return <>{children}</>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-not-allowed items-center gap-2">{children}</span>
      </TooltipTrigger>
      <TooltipContent>{t("workflow.notThisMachine", { machine })}</TooltipContent>
    </Tooltip>
  );
}
