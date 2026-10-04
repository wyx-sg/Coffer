// src/components/ui/tooltip.tsx
// Tooltip over @radix-ui/react-tooltip: a small inverted label that names a control.
// Mount ONE TooltipProvider high in the tree (Layout does); Tooltip /
// TooltipTrigger / TooltipContent compose per call site.
import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

// Foundations-Tooltips "Timing": open after 400ms of hover (keyboard focus opens
// at once — Radix does that itself), and for 600ms after one closes the next
// opens without the wait. A provider may still pass its own values.
const OPEN_DELAY_MS = 400;
const WARM_MS = 600;

function TooltipProvider({
  delayDuration = OPEN_DELAY_MS,
  skipDelayDuration = WARM_MS,
  ...props
}: React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Provider>) {
  return (
    <TooltipPrimitive.Provider
      delayDuration={delayDuration}
      skipDelayDuration={skipDelayDuration}
      {...props}
    />
  );
}
const Tooltip = TooltipPrimitive.Root;
/** Whether focus arrived from the keyboard; a browser without `:focus-visible` counts as yes. */
function keyboardFocus(el: Element): boolean {
  try {
    return el.matches(":focus-visible");
  } catch {
    return true;
  }
}

// Focus opens the tooltip only when it came from the keyboard. Focus a dialog
// moves onto its first control on open is not a request for the label, and an
// open tooltip is the topmost layer: Escape would close it, not the dialog.
const TooltipTrigger = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Trigger>
>(({ onFocus, ...props }, ref) => (
  <TooltipPrimitive.Trigger
    ref={ref}
    onFocus={(event) => {
      onFocus?.(event);
      // Radix skips its own open when the event is default-prevented.
      if (!keyboardFocus(event.currentTarget)) event.preventDefault();
    }}
    {...props}
  />
));
TooltipTrigger.displayName = TooltipPrimitive.Trigger.displayName;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content> & {
    /** The control's key (e.g. "⌘K"), set in mono at 70% after the name. */
    shortcut?: string;
  }
>(({ className, sideOffset = 6, shortcut, children, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        // Inverted chip: ink fill, page-colour text (so it flips in dark). No
        // border, no arrow — the 6px offset says where it points. One line is
        // 24 high; longer copy wraps at 240 with a 1.45 line height.
        "z-tooltip min-h-6 max-w-[240px] rounded-item bg-text px-2 py-[3px] text-xs font-medium leading-[1.45] text-surface",
        "animate-in fade-in-0 duration-fast ease-out data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-fast data-[state=closed]:ease-in",
        className,
      )}
      {...props}
    >
      {children}
      {shortcut ? <span className="ml-2 font-mono text-2xs opacity-70">{shortcut}</span> : null}
    </TooltipPrimitive.Content>
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
