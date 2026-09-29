// src/components/ui/button.tsx
// The one button (Foundations · Buttons): five kinds, three sizes, square icon-only boxes.
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// Kinds (Foundations name → variant):
//   primary      → `default`       accent fill, no border. One per view.
//   secondary    → `outline`, `secondary` (the same look; both names are in use)
//   ghost        → `ghost`         dismissive actions
//   danger       → `danger`        outline danger, where data is lost
//   danger-solid → `destructive`, `danger-solid`   the confirm button of a delete
//   `link` is inline accent text, underlined on hover.
// Sizes: `sm` 26, `default` (md) 30, `lg` 36. Icon-only boxes are square =
// height: `icon` and `icon-md` are 30 (md), `icon-sm` is 26 (sm).
// Every kind has a 1px border (transparent where the board says "no border")
// so switching kind never shifts layout by a pixel.
const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border font-label",
    "transition-[background-color,border-color,color,filter,transform] duration-fast ease-standard",
    "active:scale-[.98]",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
    "disabled:pointer-events-none disabled:opacity-disabled",
    "[&_svg]:pointer-events-none [&_svg]:size-3.5 [&_svg]:shrink-0 [&_svg]:stroke-[1.75]",
  ],
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-accent text-accent-foreground hover:brightness-[.94] active:brightness-[.88]",
        outline:
          "border-border bg-surface-raised text-text hover:bg-surface-hover active:bg-surface-selected",
        secondary:
          "border-border bg-surface-raised text-text hover:bg-surface-hover active:bg-surface-selected",
        ghost:
          "border-transparent bg-transparent text-text-muted hover:bg-surface-hover hover:text-text active:bg-surface-selected",
        danger:
          "border-border bg-surface-raised text-danger hover:bg-surface-hover active:bg-surface-selected",
        destructive:
          "border-transparent bg-danger-strong text-on-status hover:brightness-[.94] active:brightness-[.88]",
        "danger-solid":
          "border-transparent bg-danger-strong text-on-status hover:brightness-[.94] active:brightness-[.88]",
        link: "border-transparent text-accent-text underline-offset-4 hover:underline active:scale-100",
      },
      size: {
        default: "h-control-md px-3 text-sm",
        sm: "h-control-sm px-2 text-xs",
        lg: "h-control-lg px-4 text-sm [&_svg]:size-4",
        icon: "size-control-md p-0",
        "icon-md": "size-control-md p-0",
        "icon-sm": "size-control-sm p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
