// src/components/brand/CofferLogo.tsx — the Coffer mark with its "Coffer" wordmark beside it.
//
// Wordmark: Figtree 650, tracking −2%, set 0.4 × the mark away from it
// (Foundations-Brand "Wordmark"); 14px in the sidebar. The word is the product
// name, not copy, so it is not translated.
import { cn } from "@/lib/utils";
import { CofferMark } from "./CofferMark";

interface CofferLogoProps {
  /** Mark size in px (default 22). */
  size?: number;
  /** Hide the word and show the mark alone (a collapsed rail). */
  markOnly?: boolean;
  className?: string;
}

export function CofferLogo({ size = 22, markOnly = false, className }: CofferLogoProps) {
  return (
    <span
      className={cn("inline-flex items-center text-text", className)}
      style={{ gap: Math.round(size * 0.4) }}
    >
      <CofferMark size={size} />
      {markOnly ? null : (
        <span className="font-sans text-[14px] font-bold leading-none tracking-[-0.02em]">
          Coffer
        </span>
      )}
    </span>
  );
}
