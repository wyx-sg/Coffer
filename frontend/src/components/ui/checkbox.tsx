// frontend/src/components/ui/checkbox.tsx
// A minimal, dependency-free checkbox: a styled native <input type="checkbox">
// (implicit role="checkbox", full keyboard support) that also drives the
// `indeterminate` DOM property — needed for a "some rows selected" select-all.
import { useEffect, useRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  indeterminate?: boolean;
}

export function Checkbox({ className, indeterminate, ...props }: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate ?? false;
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      className={cn("size-4 cursor-pointer accent-primary align-middle", className)}
      {...props}
    />
  );
}
