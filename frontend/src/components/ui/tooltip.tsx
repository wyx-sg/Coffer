// src/components/ui/tooltip.tsx
// Tooltip over @radix-ui/react-tooltip: a small inverted label that names a control.
// Mount ONE TooltipProvider high in the tree (Layout does); Tooltip /
// TooltipTrigger / TooltipContent compose per call site.
import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

const TooltipProvider = TooltipPrimitive.Provider;
const Tooltip = TooltipPrimitive.Root;
const TooltipTrigger = TooltipPrimitive.Trigger;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        // Inverted chip: ink fill, page-colour text (so it flips in dark). No
        // border, no arrow — the 6px offset says where it points. One line is
        // 24 high; longer copy wraps at 240 with a 1.45 line height.
        "z-tooltip min-h-6 max-w-[240px] rounded-item bg-text px-2 py-1.5 text-xs font-medium leading-[1.45] text-surface",
        "animate-in fade-in-0 duration-fast ease-out data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-fast data-[state=closed]:ease-in",
        className,
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
