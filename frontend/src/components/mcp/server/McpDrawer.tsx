// src/components/mcp/server/McpDrawer.tsx — the 640 right-hand drawer of the MCP servers page: the server log and one invocation (Foundations 0.4.02).
//
// The shared drawer (ui/sheet), which starts below the window title bar (the
// scrim too), so the window's own controls stay reachable. A title and one
// muted line, a close ×, a body that scrolls, and an optional footer band.
import type { ReactNode } from "react";

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

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
  return (
    <Sheet open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <SheetContent aria-describedby={undefined} data-testid={testId}>
        <SheetHeader className="gap-0.5">
          <SheetTitle className="flex min-w-0 items-center gap-2 font-sans">{title}</SheetTitle>
          {subtitle ? <p className="text-xs text-text-muted">{subtitle}</p> : null}
        </SheetHeader>
        <SheetBody className="flex flex-col gap-3">{children}</SheetBody>
        {footer ? <SheetFooter>{footer}</SheetFooter> : null}
      </SheetContent>
    </Sheet>
  );
}
