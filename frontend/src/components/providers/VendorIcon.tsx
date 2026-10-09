// src/components/providers/VendorIcon.tsx — the 16px mark on an Add-dialog vendor button.
//
// Every vendor uses its official mark (lib/providers/brandMarks.ts): a light
// and dark file swap by the root's `data-theme`, a monochrome one inverts on
// the dark theme. Custom is a plain cube outline.
import { Box } from "lucide-react";

import { BRAND_MARKS } from "@/lib/providers/brandMarks";
import type { PresetId } from "@/lib/providers/presets";
import { cn } from "@/lib/utils";

function Img({ src, className }: { src: string; className?: string }) {
  return (
    <img
      src={src}
      alt=""
      aria-hidden
      width={16}
      height={16}
      className={cn("size-4 shrink-0 object-contain", className)}
    />
  );
}

export function VendorIcon({ id }: { id: PresetId }) {
  if (id === "custom") return <Box className="size-4 shrink-0 text-text-muted" aria-hidden />;
  const mark = BRAND_MARKS[id];
  if (mark.dark) {
    return (
      <>
        <Img src={mark.light} className="block [[data-theme=dark]_&]:hidden" />
        <Img src={mark.dark} className="hidden [[data-theme=dark]_&]:block" />
      </>
    );
  }
  const invert = mark.invert || id === "ollama";
  return <Img src={mark.light} className={invert ? "[[data-theme=dark]_&]:invert" : ""} />;
}
