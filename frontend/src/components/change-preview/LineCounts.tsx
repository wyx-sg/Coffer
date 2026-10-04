// src/components/change-preview/LineCounts.tsx
// The +N / −N line counts of a changed file, mono 11 in success / danger; nothing when both are zero.
import { cn } from "@/lib/utils";

interface Props {
  added?: number;
  removed?: number;
  className?: string;
}

export function LineCounts({ added, removed, className }: Props) {
  const hasAdded = (added ?? 0) > 0;
  const hasRemoved = (removed ?? 0) > 0;
  if (!hasAdded && !hasRemoved) return null;
  return (
    <span className={cn("inline-flex shrink-0 gap-1.5 font-mono text-2xs", className)}>
      {hasAdded ? <span className="text-success">+{added}</span> : null}
      {hasRemoved ? <span className="text-danger">−{removed}</span> : null}
    </span>
  );
}
