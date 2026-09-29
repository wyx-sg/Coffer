// src/components/providers/StepMarker.tsx — "1 Endpoint — 2 Models": where the Add dialog is.
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export function StepMarker({ step }: { step: 1 | 2 }) {
  const { t } = useTranslation();
  const item = (n: 1 | 2, label: string) => (
    <span
      aria-current={step === n ? "step" : undefined}
      className={cn(
        "inline-flex items-center gap-[7px] text-xs",
        step === n ? "font-semibold text-text" : "font-book text-text-muted",
      )}
    >
      <span
        className={cn(
          "inline-flex size-[18px] items-center justify-center rounded-full border text-2xs font-heavy",
          step === n ? "border-accent text-accent-text" : "border-border text-text-muted",
        )}
      >
        {n}
      </span>
      {label}
    </span>
  );
  return (
    <div className="flex items-center gap-2.5">
      {item(1, t("providers.add.stepEndpoint"))}
      <span aria-hidden className="h-px w-6 bg-border" />
      {item(2, t("providers.add.stepModels"))}
    </div>
  );
}
