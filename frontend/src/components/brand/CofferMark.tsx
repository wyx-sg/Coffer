// src/components/brand/CofferMark.tsx — the Coffer logo: the Stroke C mark drawn in theme colours.
//
// An open-right rounded square drawn with the nav-icon pen (1.75 on the 24
// grid, round caps and joins) around a single accent dot (Foundations-Brand).
// The stroke is currentColor, so it takes the ink of whatever text colour it
// sits in; the dot is the accent. The stroke never renders below 1.5px, so
// small marks thicken it — 2.25 at the 16px favicon size.
import { cn } from "@/lib/utils";
import { cofferMarkStroke } from "./cofferMarkStroke";

interface CofferMarkProps {
  /** Rendered size in px (default 22, the sidebar size). */
  size?: number;
  className?: string;
}

export function CofferMark({ size = 22, className }: CofferMarkProps) {
  const stroke = cofferMarkStroke(size);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden
      data-coffer-mark=""
      className={cn("shrink-0 text-text", className)}
    >
      <path
        d="M20 8.5V7a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v10a4 4 0 0 0 4 4h8a4 4 0 0 0 4-4v-1.5"
        fill="none"
        stroke="currentColor"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="1.9" fill="none" strokeWidth={stroke} className="stroke-accent" />
    </svg>
  );
}
