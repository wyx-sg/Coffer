// src/components/ui/switch.tsx
// The on/off switch (Foundations · Selection): 30×18 track, 14px knob, accent only when on.
import * as React from "react";
import * as SwitchPrimitives from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

// A switch acts now (it saves on toggle); a choice that waits for a button is
// a checkbox. The knob sits 2px inside the track and travels 12px.
const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    className={cn(
      "peer inline-flex h-[18px] w-control-md shrink-0 cursor-pointer items-center rounded-full p-0.5",
      "transition-colors duration-fast ease-standard",
      "data-[state=checked]:bg-accent data-[state=unchecked]:bg-control-off",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
      "disabled:cursor-default disabled:opacity-disabled",
      className,
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitives.Thumb
      className={cn(
        "pointer-events-none block size-3.5 rounded-full bg-knob shadow-knob ring-0",
        "transition-transform duration-fast ease-standard",
        "data-[state=checked]:translate-x-3 data-[state=unchecked]:translate-x-0",
      )}
    />
  </SwitchPrimitives.Root>
));
Switch.displayName = SwitchPrimitives.Root.displayName;

export { Switch };
