// src/components/channel/PlatformMark.tsx — a chat platform shown as a small
// two-letter tile (ST SeaTalk, TG Telegram) on the neutral chip, the way the
// Channels list, a channel's header and a conversation's source badge all show
// it. Colour stays reserved for state, so the tile is the same for every
// platform; the name beside it says which one (lib/chat/mirror `platformName`).
import { cn } from "@/lib/utils";

import { platformName } from "@/lib/chat/mirror";

const INITIALS: Record<string, string> = { seatalk: "ST", telegram: "TG" };

/** A platform key as its product name (`seatalk` → `SeaTalk`). */
export const platformLabel = platformName;

interface Props {
  /** The platform key (`seatalk`, `telegram`); anything else shows its first letters. */
  platform: string;
  size?: "sm" | "md";
  className?: string;
}

export function PlatformMark({ platform, size = "sm", className }: Props) {
  const initials = INITIALS[platform] ?? platform.slice(0, 2).toUpperCase();
  return (
    <span
      aria-hidden
      data-platform={platform}
      className={cn(
        "inline-flex shrink-0 items-center justify-center bg-chip font-semibold text-text-muted",
        size === "sm" ? "h-[18px] w-[22px] rounded-sm text-2xs" : "size-7 rounded-md text-2xs",
        className,
      )}
    >
      {initials}
    </span>
  );
}
