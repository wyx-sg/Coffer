// src/components/HelpTip.tsx — the small "?" beside a label that holds the
// explanation a surface owes its reader but should not print inline.
//
// The rule it serves: what a page prints is only what the reader needs to act —
// state, faults, the one line that says what a button does. Everything that
// explains WHY (a handover window, what re-pairing replaces) is still on the
// surface, one hover or tap away, rather than a paragraph under every control.
//
// A Popover rather than a Tooltip, because the content is prose a reader may
// want to keep open and select, and because a tooltip never opens on touch. It
// opens on hover after a short delay (and stays open while the pointer moves
// into it), and a click, Enter or Space pins it open until the next click,
// Escape or an outside click. Focus is never moved into it: a hover must not
// steal the caret from whatever the reader was typing in.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CircleHelp } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const OPEN_DELAY_MS = 150;
const CLOSE_DELAY_MS = 150;

interface Props {
  /** What the popover explains — usually one or two short paragraphs. */
  children: ReactNode;
  /** The button's accessible name; defaults to "More info". */
  label?: string;
  className?: string;
}

export function HelpTip({ children, label, className }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  // Opened by a click (or the keyboard) rather than by passing over it: a
  // pinned tip ignores the pointer leaving, and the next click closes it.
  const [pinned, setPinned] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = () => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  };
  useEffect(() => clear, []);

  const hoverOpen = (e: React.PointerEvent) => {
    // A touch fires a click right after; let the click decide, or the tip
    // would open on the pointer event and close again on the click.
    if (e.pointerType === "touch") return;
    clear();
    timer.current = setTimeout(() => setOpen(true), OPEN_DELAY_MS);
  };
  const hoverClose = (e: React.PointerEvent) => {
    if (e.pointerType === "touch" || pinned) return;
    clear();
    timer.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        // Radix reports Escape and outside clicks here; the trigger's own
        // toggle is handled below, so only a close ever arrives.
        if (!next) {
          clear();
          setOpen(false);
          setPinned(false);
        }
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label ?? t("common.moreInfo")}
          className={cn(
            "inline-flex size-5 shrink-0 items-center justify-center rounded-full text-text-subtle transition-colors duration-fast hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            className,
          )}
          onPointerEnter={hoverOpen}
          onPointerLeave={hoverClose}
          onClick={(e) => {
            // Replaces Radix's toggle: a tip the pointer already opened is
            // pinned by the click, not closed by it.
            e.preventDefault();
            clear();
            if (pinned) {
              setPinned(false);
              setOpen(false);
            } else {
              setPinned(true);
              setOpen(true);
            }
          }}
        >
          <CircleHelp className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="space-y-2"
        onOpenAutoFocus={(e) => e.preventDefault()}
        onPointerEnter={clear}
        onPointerLeave={hoverClose}
      >
        {children}
      </PopoverContent>
    </Popover>
  );
}
