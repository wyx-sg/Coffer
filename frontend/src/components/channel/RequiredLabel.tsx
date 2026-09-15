// frontend/src/components/channel/RequiredLabel.tsx
// The one way a channel form marks a field as required: the label plus a mark
// drawn after it. The mark is a pseudo-element, so the label's text — and with
// it the field's accessible name — stays just the word; `aria-required` on the
// input is what assistive tech reads. Beneath the field, `FieldError` renders
// the translated message a zod issue mapped to, or nothing.
import type { ComponentProps } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const REQUIRED_MARK = "after:ml-0.5 after:text-destructive after:content-['*']";

export function RequiredLabel({ className, ...props }: ComponentProps<typeof Label>) {
  return <Label className={cn(REQUIRED_MARK, className)} {...props} />;
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-destructive" role="alert">
      {message}
    </p>
  );
}
