// frontend/src/components/channel/ChannelPlatformCards.tsx
// The platforms a channel can connect: each one's logo and name, what
// connecting it takes, what it is for and what it can do in a chat. Shared by
// the first-run page (a bordered list whose rows lead on, with a chevron) and
// step 1 of Add channel (radio rows, one chosen), so both offer the same choice
// in the same words. Every row is a button.
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import type { ChannelType } from "@/lib/api/channels";
import { cn } from "@/lib/utils";
import { CAPABILITIES, PLATFORMS } from "./channelPlatforms";
import { PlatformMark, platformLabel } from "./PlatformMark";

interface Props {
  platforms?: readonly ChannelType[];
  /** `radio`: stacked cards with a radio dot (the add dialog's step 1).
   *  `list`: one bordered container, rows ending in a chevron (first run). */
  variant: "radio" | "list";
  /** The chosen row, outlined (radio only). */
  selected?: ChannelType | null;
  onChoose: (platform: ChannelType) => void;
}

function Tags({ platform }: { platform: ChannelType }) {
  const { t } = useTranslation();
  return (
    <span className="flex flex-wrap gap-1">
      {(CAPABILITIES[platform] ?? []).map((c) => (
        <span
          key={c}
          className="inline-flex h-5 items-center rounded-[5px] bg-chip px-[7px] text-2xs text-text-muted"
        >
          {t(`channels.platforms.capabilities.${c}`)}
        </span>
      ))}
    </span>
  );
}

export function ChannelPlatformCards({
  platforms = PLATFORMS,
  variant,
  selected = null,
  onChoose,
}: Props) {
  const { t } = useTranslation();
  const list = variant === "list";
  return (
    <div
      className={cn(
        "flex flex-col",
        list
          ? "divide-y divide-border-subtle overflow-hidden rounded-xl border border-border"
          : "gap-2.5",
      )}
    >
      {platforms.map((p) => (
        <button
          key={p}
          type="button"
          aria-pressed={list ? undefined : selected === p}
          onClick={() => onChoose(p)}
          className={cn(
            "flex gap-3 text-left transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            list
              ? "items-center px-4 py-3.5"
              : cn(
                  "items-start rounded-xl border p-3.5",
                  selected === p
                    ? "border-accent bg-accent-soft"
                    : "border-border bg-surface-raised",
                ),
          )}
        >
          {list ? null : (
            <span
              aria-hidden
              className={cn(
                "mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full border",
                selected === p ? "border-[5px] border-accent" : "border-text-subtle",
              )}
            />
          )}
          <PlatformMark platform={p} size="lg" />
          <span className="flex min-w-0 grow flex-col gap-1.5">
            <span className="flex items-baseline gap-2">
              <span className="text-sm font-semibold text-text">{platformLabel(p)}</span>
              {list ? null : (
                <span className="ml-auto text-xs text-text-subtle">
                  {t(`channels.platforms.${p}.needs`)}
                </span>
              )}
            </span>
            <span className="text-xs text-text-muted">{t(`channels.platforms.${p}.body`)}</span>
            <Tags platform={p} />
          </span>
          {list ? (
            <>
              <span className="whitespace-nowrap text-xs text-text-subtle">
                {t(`channels.platforms.${p}.needs`)}
              </span>
              <ChevronRight className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
            </>
          ) : null}
        </button>
      ))}
    </div>
  );
}
