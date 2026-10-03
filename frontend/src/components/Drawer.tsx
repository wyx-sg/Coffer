// src/components/Drawer.tsx — the one right-hand drawer (Foundations 0.4.02).
//
// Reads a record or a log without leaving the list: 640 wide, from the title
// bar down, the page behind dimmed to the 32% scrim. Esc, a click outside or ✕
// closes it, and focus returns to the row that opened it. The header carries
// the title (15/650), an optional mono subtitle and, for a list of records,
// previous / next (also the ↑ / ↓ keys while the drawer is open, unless the
// person is typing). Only the body scrolls; the footer, when given, holds the
// next step on the right and an optional quiet fact on the left.
import { ArrowDown, ArrowUp, X } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  /** A mono line under the title: an id, a path, a time. */
  subtitle?: ReactNode;
  /** Step through the list's records; give both (or neither) so the pair always shows. */
  onPrevious?: () => void;
  onNext?: () => void;
  /** False at the first / last record. */
  hasPrevious?: boolean;
  hasNext?: boolean;
  /** The next step's buttons, right-aligned. */
  footer?: ReactNode;
  /** A quiet fact at the footer's left ("3 lines"). */
  footerNote?: ReactNode;
  bodyClassName?: string;
  children: ReactNode;
}

const TYPING = "input, textarea, select, [contenteditable='true']";

export function Drawer({
  open,
  onOpenChange,
  title,
  subtitle,
  onPrevious,
  onNext,
  hasPrevious = true,
  hasNext = true,
  footer,
  footerNote,
  bodyClassName,
  children,
}: Props) {
  const { t } = useTranslation();
  const stepping = onPrevious !== undefined || onNext !== undefined;

  const onKeyDown = (event: KeyboardEvent) => {
    if (!stepping || (event.target as HTMLElement).closest(TYPING)) return;
    if (event.key === "ArrowUp" && hasPrevious) {
      event.preventDefault();
      onPrevious?.();
    } else if (event.key === "ArrowDown" && hasNext) {
      event.preventDefault();
      onNext?.();
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        showClose={false}
        onKeyDown={onKeyDown}
        // No subtitle means no description to point at.
        {...(subtitle ? {} : { "aria-describedby": undefined })}
      >
        <SheetHeader className="flex-row items-start gap-2 pr-3.5">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <SheetTitle className="truncate font-sans text-md font-bold">{title}</SheetTitle>
            {subtitle ? (
              <SheetDescription className="truncate font-mono">{subtitle}</SheetDescription>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-0.5">
            {stepping ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("drawer.previous")}
                  disabled={!hasPrevious}
                  onClick={onPrevious}
                >
                  <ArrowUp aria-hidden />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("drawer.next")}
                  disabled={!hasNext}
                  onClick={onNext}
                >
                  <ArrowDown aria-hidden />
                </Button>
              </>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t("common.close")}
              onClick={() => onOpenChange(false)}
            >
              <X aria-hidden />
            </Button>
          </div>
        </SheetHeader>
        <SheetBody className={cn("py-4", bodyClassName)}>{children}</SheetBody>
        {footer || footerNote ? (
          <SheetFooter className="justify-between">
            <span className="min-w-0 truncate text-xs text-text-subtle">{footerNote}</span>
            <div className="flex items-center gap-2">{footer}</div>
          </SheetFooter>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
