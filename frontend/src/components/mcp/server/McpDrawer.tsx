// src/components/mcp/server/McpDrawer.tsx — the 640 right-hand drawer of the MCP servers page: the server log and one invocation (Foundations 0.4.02).
//
// It starts below the 44px title bar (the scrim too), so the window's own
// controls stay reachable. A title and one muted line, a close ×, a body that
// scrolls, and an optional footer band.
import type { ReactNode } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  testId: string;
}

export function McpDrawer({ open, onClose, title, subtitle, children, footer, testId }: Props) {
  const { t } = useTranslation();
  return (
    <DialogPrimitive.Root open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-x-0 bottom-0 top-11 z-dialog bg-scrim" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          data-testid={testId}
          className="fixed bottom-0 right-0 top-11 z-dialog flex w-[min(640px,100vw)] flex-col border-l border-border bg-surface-raised text-sm text-text shadow-overlay outline-none"
        >
          <div className="flex items-start gap-3 border-b border-border-subtle px-5 py-4">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <DialogPrimitive.Title className="flex min-w-0 items-center gap-2 text-md font-bold">
                {title}
              </DialogPrimitive.Title>
              {subtitle ? <p className="text-xs text-text-muted">{subtitle}</p> : null}
            </div>
            <DialogPrimitive.Close
              aria-label={t("common.close")}
              className="inline-flex size-7 items-center justify-center rounded-item text-text-muted hover:bg-surface-hover hover:text-text"
            >
              <X className="size-4" aria-hidden />
            </DialogPrimitive.Close>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
            {children}
          </div>
          {footer ? (
            <div className="flex items-center gap-2 border-t border-border-subtle bg-surface-footer px-5 py-3">
              {footer}
            </div>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
