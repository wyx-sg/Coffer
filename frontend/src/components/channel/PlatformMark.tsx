// src/components/channel/PlatformMark.tsx — a chat platform shown as a small
// tile on the neutral chip — the platform's mark (SeaTalk's and Telegram's own
// logos, as supplied by their sites), or two letters for a platform with none, the way the
// Channels list, a channel's header and a conversation's source badge all show
// it. Colour stays reserved for state, so the tile is the same for every
// platform; the name beside it says which one (lib/channels/platformName).
import seatalkUrl from "@/assets/brand/seatalk-logo.png";
import telegramUrl from "@/assets/brand/telegram-logo.svg";
import { cn } from "@/lib/utils";

import { platformName } from "@/lib/channels/platformName";

const MARKS: Record<string, string> = { seatalk: seatalkUrl, telegram: telegramUrl };
const INITIALS: Record<string, string> = { seatalk: "ST", telegram: "TG" };

/** A platform key as its product name (`seatalk` → `SeaTalk`). */
export const platformLabel = platformName;

interface Props {
  /** The platform key (`seatalk`, `telegram`); anything else shows its first letters. */
  platform: string;
  /** `lg` is the bare logo at 28px, as the platform cards show it. */
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function PlatformMark({ platform, size = "sm", className }: Props) {
  const initials = INITIALS[platform] ?? platform.slice(0, 2).toUpperCase();
  if (size === "lg") {
    return (
      <span
        aria-hidden
        data-platform={platform}
        className={cn(
          "inline-flex size-7 shrink-0 items-center justify-center overflow-hidden bg-chip text-2xs font-semibold text-text-muted",
          platform === "telegram" ? "rounded-full" : "rounded-[4px]",
          MARKS[platform] && "bg-transparent",
          className,
        )}
      >
        {MARKS[platform] ? (
          <img src={MARKS[platform]} alt="" className="block size-full object-contain" />
        ) : (
          initials
        )}
      </span>
    );
  }
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
      {MARKS[platform] ? (
        <img src={MARKS[platform]} alt="" className="block h-[78%] w-[78%] object-contain" />
      ) : (
        initials
      )}
    </span>
  );
}
