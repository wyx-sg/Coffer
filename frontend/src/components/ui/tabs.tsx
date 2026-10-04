// src/components/ui/tabs.tsx
// Underline tabs over @radix-ui/react-tabs: a hairline rail, ink underline on the active tab.
import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

const Tabs = TabsPrimitive.Root;

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "flex h-[38px] items-stretch gap-[22px] border-b border-border text-text-muted",
      className,
    )}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

// The underline sits on the rail (-mb-px) so the active tab reads as attached
// to it; the focus ring hugs the label, not the whole 38px cell.
const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "group relative -mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 border-transparent text-sm font-book text-text-muted outline-none transition-colors duration-fast",
      "hover:text-text disabled:pointer-events-none disabled:opacity-disabled",
      "data-[state=active]:border-text data-[state=active]:font-label data-[state=active]:text-text",
      className,
    )}
    {...props}
  >
    <span className="inline-flex items-center gap-1.5 rounded-xs px-0.5 group-focus-visible:ring-2 group-focus-visible:ring-focus-ring">
      {children}
    </span>
  </TabsPrimitive.Trigger>
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn("mt-4 focus-visible:outline-none", className)}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
