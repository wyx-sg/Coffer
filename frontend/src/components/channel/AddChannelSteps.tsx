// frontend/src/components/channel/AddChannelSteps.tsx
// The add dialog's stepper — 1 Platform · 2 Connect · 3 Pair — and its first
// step: the platform rows and one line on what a channel is. The stepper
// carries no accent colour: a finished step is a grey check, the current one a
// dark outlined number, the rest grey numbers.
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { ChannelType } from "@/lib/api/channels";
import { cn } from "@/lib/utils";
import { ADD_STEPS, type AddStep } from "./addChannel";
import { ChannelPlatformCards } from "./ChannelPlatformCards";

export function AddChannelStepper({ step }: { step: AddStep }) {
  const { t } = useTranslation();
  const current = ADD_STEPS.indexOf(step);
  return (
    <ol className="flex items-center gap-2.5 text-xs" aria-label={t("channels.add.stepsLabel")}>
      {ADD_STEPS.map((s, i) => (
        <li key={s} aria-current={i === current ? "step" : undefined} className="contents">
          {i > 0 ? <span aria-hidden className="h-px w-7 bg-border" /> : null}
          <span
            className={cn(
              "inline-flex items-center gap-1.5",
              i === current
                ? "font-semibold text-text"
                : i < current
                  ? "text-text-muted"
                  : "text-text-subtle",
            )}
          >
            {i < current ? (
              <span
                aria-hidden
                className="inline-flex size-[18px] items-center justify-center text-text-subtle"
              >
                <Check className="size-3.5" />
              </span>
            ) : (
              <span
                aria-hidden
                className={cn(
                  "inline-flex size-[18px] items-center justify-center rounded-full text-2xs",
                  i === current
                    ? "border-[1.5px] border-text font-semibold text-text"
                    : "border border-border text-text-subtle",
                )}
              >
                {i + 1}
              </span>
            )}
            {t(`channels.add.steps.${s}`)}
          </span>
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
  return (
    <div className="space-y-3">
      <ChannelPlatformCards variant="radio" selected={selected} onChoose={onSelect} />
      <p className="text-xs leading-normal text-text-muted">{t("channels.add.platformHint")}</p>
    </div>
  );
}
