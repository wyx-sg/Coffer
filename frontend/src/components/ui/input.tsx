// src/components/ui/input.tsx
// The 30px text field (Foundations · Inputs).
import * as React from "react";
import { cn } from "@/lib/utils";
import { fieldClass, fieldReadOnlyClass } from "@/components/ui/field-classes";

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          fieldClass,
          fieldReadOnlyClass,
          "flex h-control-md px-2.5 py-0 caret-accent",
          "file:border-0 file:bg-transparent file:text-sm file:font-label file:text-text",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
