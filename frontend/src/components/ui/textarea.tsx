// src/components/ui/textarea.tsx
// The multi-line text field: the input's field look, padding 8/10, line-height 1.5, min three lines.
import * as React from "react";
import { cn } from "@/lib/utils";
import { fieldClass, fieldReadOnlyClass } from "@/components/ui/field-classes";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentPropsWithoutRef<"textarea">>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          fieldClass,
          fieldReadOnlyClass,
          // 3 lines × 19.5px + 16px padding + 2px border.
          "flex min-h-[77px] px-2.5 py-2 leading-normal caret-accent",
          className,
        )}
        {...props}
      />
    );
  },
);
Textarea.displayName = "Textarea";

export { Textarea };
