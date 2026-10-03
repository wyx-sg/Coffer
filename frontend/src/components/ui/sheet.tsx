// src/components/ui/sheet.tsx
// Drawer over @radix-ui/react-dialog: scrim, a raised panel on the right, header / scrolling body / footer band.
// Scrim and panel start below the 44px title bar (Foundations 0.4.02), so the window controls stay usable.
import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

const Sheet = DialogPrimitive.Root;

// The panel is a column: the header and footer keep their place and only the
// body between them scrolls, so Save stays on screen however long the form.
const SheetContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => {
  const { t } = useTranslation();
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay
        className={cn(
          "fixed inset-x-0 bottom-0 top-11 z-dialog bg-scrim",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:duration-base",
          "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-fast",
        )}
      />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          "fixed bottom-0 right-0 top-11 z-dialog flex w-full max-w-[640px] flex-col bg-surface-raised text-sm text-text shadow-overlay outline-none",
          "data-[state=open]:animate-in data-[state=open]:slide-in-from-right data-[state=open]:duration-slow data-[state=open]:ease-out",
          "data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=closed]:duration-fast data-[state=closed]:ease-in",
          className,
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-3.5 top-[18px] inline-flex size-6 items-center justify-center rounded-item text-text-subtle transition-colors duration-fast hover:bg-surface-hover hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring">
          <X className="size-4" />
          <span className="sr-only">{t("common.close")}</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
});
SheetContent.displayName = "SheetContent";

function SheetHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-col gap-1 border-b border-border-subtle px-5 py-4 pr-12", className)}
      {...props}
    />
  );
}

function SheetBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-h-0 flex-1 overflow-y-auto px-5 py-4", className)} {...props} />;
}

function SheetFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 border-t border-border-subtle bg-surface-footer px-5 py-3",
        className,
      )}
      {...props}
    />
  );
}

const SheetTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("font-mono text-md font-bold text-text", className)}
    {...props}
  />
));
SheetTitle.displayName = "SheetTitle";

const SheetDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-xs text-text-muted", className)}
    {...props}
  />
));
SheetDescription.displayName = "SheetDescription";

export { Sheet, SheetContent, SheetHeader, SheetBody, SheetFooter, SheetTitle, SheetDescription };
