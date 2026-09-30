// frontend/src/components/channel/AddChannelSteps.tsx
// The add dialog's stepper — 1 Platform · 2 Connect · 3 Pair — and its first
// step: the platform cards under a filter, and one line on what a channel is.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";

import { SearchInput } from "@/components/SearchInput";
import type { ChannelType } from "@/lib/api/channels";
import { cn } from "@/lib/utils";
import { ADD_STEPS, type AddStep } from "./addChannel";
import { ChannelPlatformCards } from "./ChannelPlatformCards";
import { PLATFORMS, usePlatformSearchText } from "./channelPlatforms";

export function AddChannelStepper({ step }: { step: AddStep }) {
  const { t } = useTranslation();
  const current = ADD_STEPS.indexOf(step);
  return (
    <ol className="flex items-center gap-3 text-xs" aria-label={t("channels.add.stepsLabel")}>
      {ADD_STEPS.map((s, i) => (
        <li
          key={s}
          aria-current={i === current ? "step" : undefined}
          className={cn(
            "inline-flex items-center gap-1.5",
            i === current ? "font-label text-text" : "text-text-muted",
          )}
        >
          <span
            aria-hidden
            className={cn(
              "inline-flex size-[18px] items-center justify-center rounded-full text-2xs font-semibold",
              i === current ? "bg-accent text-accent-foreground" : "bg-chip text-text-muted",
            )}
          >
            {i < current ? <Check className="size-3" /> : i + 1}
          </span>
          {t(`channels.add.steps.${s}`)}
        </li>
      ))}
    </ol>
  );
}

interface PlatformStepProps {
  selected: ChannelType | null;
  onSelect: (platform: ChannelType) => void;
}

export function AddChannelPlatformStep({ selected, onSelect }: PlatformStepProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const searchText = usePlatformSearchText();
  const q = query.trim().toLowerCase();
  const shown = PLATFORMS.filter((p) => !q || searchText(p).includes(q));
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <SearchInput
          className="flex-1"
          value={query}
          onChange={setQuery}
          placeholder={t("channels.add.filter")}
          ariaLabel={t("channels.add.filter")}
        />
        <span className="shrink-0 text-xs text-text-muted">
          {t("channels.platforms.count", { count: shown.length })}
        </span>
      </div>
      <ChannelPlatformCards platforms={shown} selected={selected} onChoose={onSelect} />
      <p className="text-xs leading-normal text-text-muted">{t("channels.add.platformHint")}</p>
    </div>
  );
}
