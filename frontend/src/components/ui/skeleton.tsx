// src/components/ui/skeleton.tsx
// shadcn-style loading placeholder: a pulsing muted block sized by the caller
// so a surface can keep its real shape (row height, card footprint) while data
// resolves instead of rendering nothing.
import * as React from "react";

import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div aria-hidden className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />
  );
}

export { Skeleton };
