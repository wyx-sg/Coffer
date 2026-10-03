// src/components/providers/ProviderWelcome.tsx — first run: no provider yet.
//
// A centred empty state — "No model providers yet" — and three ways in: an
// Anthropic-compatible endpoint, an OpenAI-compatible one, or a runtime on this
// Mac, each opening Add with that vendor chosen. The header's Add provider is
// the page's primary button, so none repeats it here.
import { Box, Laptop, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { PresetId } from "@/lib/providers/presets";

interface Props {
  onAdd: (preset: PresetId) => void;
}

const OPTIONS: { preset: PresetId; key: string; icon: LucideIcon }[] = [
  { preset: "anthropic", key: "anthropic", icon: Box },
  { preset: "openai", key: "openai", icon: Box },
  { preset: "ollama", key: "local", icon: Laptop },
];

export function ProviderWelcome({ onAdd }: Props) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-3xl flex-col items-center gap-6 px-8 pb-10 pt-20">
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="inline-flex size-10 items-center justify-center rounded-lg bg-chip text-text-muted">
          <Box className="size-[18px]" aria-hidden />
        </span>
        <h2 className="mt-2 text-md font-bold text-text">{t("providers.welcome.title")}</h2>
        <p className="max-w-md text-sm text-text-muted">{t("providers.welcome.body")}</p>
      </div>
      <div className="grid w-full gap-3 sm:grid-cols-3">
        {OPTIONS.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => onAdd(o.preset)}
            className="flex items-start gap-2.5 rounded-lg border border-border-subtle bg-surface-raised p-3.5 text-left outline-none hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-md bg-chip text-text-muted">
              <o.icon className="size-3.5" aria-hidden />
            </span>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="text-sm font-label text-text">
                {t(`providers.welcome.${o.key}.title`)}
              </span>
              <span className="text-xs text-text-muted">
                {t(`providers.welcome.${o.key}.body`)}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
