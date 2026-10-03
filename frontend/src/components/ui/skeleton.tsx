// src/components/ui/skeleton.tsx
// Loading placeholder: a sunken r4 bar sized by the caller so a surface keeps
// its real shape (row height, card footprint) while data resolves. It is
// invisible for the first 300ms, so a fast load never flickers; then a soft
// highlight sweeps it (animate-shimmer), and under reduced motion it holds
// still (animate-appear keeps the 300ms wait).
import * as React from "react";

import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn(
        "animate-shimmer rounded-xs bg-surface-sunken bg-gradient-to-r from-surface-sunken via-surface-raised to-surface-sunken bg-[length:200%_100%] motion-reduce:animate-appear",
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
