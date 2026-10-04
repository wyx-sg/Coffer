// src/components/custom-tools/FormField.tsx — one field of a one-column form: label above, help or error below.
//
// Foundations-Forms: 12/550 label with the required mark, the control at full
// width, 6 between label, field and help; an error adds a line, it replaces
// nothing.
import type { ReactNode } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface Props {
  label: ReactNode;
  /** The control's id, so the label names it. */
  htmlFor?: string;
  required?: boolean;
  help?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function FormField({ label, htmlFor, required, help, error, children, className }: Props) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor} required={required}>
        {label}
      </Label>
      {children}
      {help ? <p className="text-xs text-text-muted">{help}</p> : null}
      {error ? (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
