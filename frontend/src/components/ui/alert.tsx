// src/components/ui/alert.tsx
// Banner: a status-tinted r8 strip — 15px status icon, 13/550 title, 12 muted body.
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// The icon is the first child; everything after it is indented past it
// (12 inset + 15 icon + 10 gap), so callers just drop an icon in front.
const alertVariants = cva(
  "relative w-full rounded-lg px-3 py-2.5 text-xs text-text-muted [&>svg]:absolute [&>svg]:left-3 [&>svg]:top-[12px] [&>svg]:size-[15px] [&>svg~*]:pl-[25px]",
  {
    variants: {
      variant: {
        default: "bg-accent-soft [&>svg]:text-accent-text",
        info: "bg-accent-soft [&>svg]:text-accent-text",
        destructive: "bg-danger-soft [&>svg]:text-danger",
        error: "bg-danger-soft [&>svg]:text-danger",
        warning: "bg-warning-soft [&>svg]:text-warning",
        success: "bg-success-soft [&>svg]:text-success",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div ref={ref} role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
));
Alert.displayName = "Alert";

const AlertTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h5 ref={ref} className={cn("mb-0.5 text-sm font-label text-text", className)} {...props} />
  ),
);
AlertTitle.displayName = "AlertTitle";

const AlertDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("text-xs leading-[1.45] text-text-muted [&_p]:leading-[1.45]", className)}
    {...props}
  />
));
AlertDescription.displayName = "AlertDescription";

export { Alert, AlertTitle, AlertDescription };
