// frontend/src/components/channel/ChannelPlatformCards.tsx
// The platforms a channel can connect, as cards: what each is for, what it
// can do in a chat, and what connecting it takes. Shared by the first-run
// page and step 1 of Add channel, so both offer the same choice in the same
// words. A card is a button; choosing one opens (or advances) the add flow.
import { useTranslation } from "react-i18next";

import type { ChannelType } from "@/lib/api/channels";
import { cn } from "@/lib/utils";
import { CAPABILITIES, PLATFORMS } from "./channelPlatforms";
import { PlatformMark, platformLabel } from "./PlatformMark";

interface Props {
  platforms?: readonly ChannelType[];
  /** The chosen card, highlighted (step 1 of the add dialog). */
  selected?: ChannelType | null;
  onChoose: (platform: ChannelType) => void;
}

export function ChannelPlatformCards({ platforms = PLATFORMS, selected = null, onChoose }: Props) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {platforms.map((p) => (
        <button
          key={p}
          type="button"
          aria-pressed={selected === p}
          onClick={() => onChoose(p)}
          className={cn(
            "flex flex-col gap-2.5 rounded-xl border bg-surface-raised p-3.5 text-left transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            selected === p ? "border-accent" : "border-border-subtle",
          )}
        >
          <span className="flex items-center gap-2.5">
            <PlatformMark platform={p} size="md" />
            <span className="text-sm font-semibold text-text">{platformLabel(p)}</span>
          </span>
          <span className="text-xs leading-normal text-text-muted">
            {t(`channels.platforms.${p}.body`)}
          </span>
          <span className="flex flex-wrap gap-1">
            {(CAPABILITIES[p] ?? []).map((c) => (
              <span
                key={c}
                className="rounded-sm bg-chip px-1.5 py-0.5 text-2xs font-label text-text-muted"
              >
                {t(`channels.platforms.capabilities.${c}`)}
              </span>
            ))}
          </span>
          <span className="text-xs text-text-muted">
            {t("channels.platforms.toConnect")}{" "}
            <span className="font-label text-text">{t(`channels.platforms.${p}.needs`)}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
