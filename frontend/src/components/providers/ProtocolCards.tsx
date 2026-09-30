// src/components/providers/ProtocolCards.tsx — pick a wire by what can use it: "OpenAI-compatible — Codex, chat and Coffer's engine".
import { useTranslation } from "react-i18next";

import type { Protocol } from "@/lib/api/providers";
import { cn } from "@/lib/utils";

interface Props {
  value: Protocol;
  options: readonly Protocol[];
  onChange: (value: Protocol) => void;
}

export function ProtocolCards({ value, options, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div
      role="radiogroup"
      aria-label={t("providers.fields.protocol")}
      className="flex flex-wrap gap-2.5"
    >
      {options.map((p) => (
        <button
          key={p}
          type="button"
          role="radio"
          aria-checked={p === value}
          onClick={() => onChange(p)}
          className={cn(
            "flex min-w-[180px] flex-1 flex-col gap-0.5 rounded-lg border p-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            p === value ? "border-accent bg-accent-soft" : "border-border hover:bg-surface-hover",
          )}
        >
          <span className="text-sm font-semibold text-text">
            {t(`providers.add.protocols.${p}.title`)}
          </span>
          <span className="text-xs text-text-muted">{t(`providers.add.protocols.${p}.body`)}</span>
        </button>
      ))}
    </div>
  );
}
