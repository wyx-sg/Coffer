// src/components/ui/popover.tsx
// Popover over @radix-ui/react-popover: a raised 260-wide help/detail box, 6 below its trigger.
import * as React from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { cn } from "@/lib/utils";

const Popover = PopoverPrimitive.Root;
const PopoverTrigger = PopoverPrimitive.Trigger;

const PopoverContent = React.forwardRef<
  React.ElementRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "start", sideOffset = 6, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        "z-menu w-[260px] rounded-xl bg-surface-raised p-3 text-xs text-text-muted shadow-overlay outline-none",
        "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:duration-base data-[state=open]:ease-out",
        "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-fast data-[state=closed]:ease-in",
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
));
PopoverContent.displayName = PopoverPrimitive.Content.displayName;

export { Popover, PopoverTrigger, PopoverContent };
