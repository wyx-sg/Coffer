// src/components/ui/badge.tsx
// The Foundations "chip": a 20px label for a kind, a scope or a toned state.
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// Variants → chip looks:
//   `secondary` neutral chip (the common case: transport, scope, counts)
//   `default`   accent chip (accent-soft fill, accent text)
//   `outline`   hairline chip on the raised surface
//   `destructive` / `success` / `warning`  toned chip: *-soft fill + status colour
// Colour is for state only — a label that is not a state belongs on `secondary`.
const badgeVariants = cva(
  "inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-sm border px-[7px] text-2xs font-label",
  {
    variants: {
      variant: {
        default: "border-transparent bg-accent-soft text-accent-text",
        secondary: "border-transparent bg-chip text-text-muted",
        destructive: "border-transparent bg-danger-soft text-danger",
        success: "border-transparent bg-success-soft text-success",
        warning: "border-transparent bg-warning-soft text-warning",
        outline: "border-border bg-surface-raised text-text-muted",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
