// src/components/ui/truncated-text.tsx
// One-line text that ends in an ellipsis when its cell is too narrow, with the
// full text in a tooltip — but only when something is actually cut off.
// `TruncatedText` clips the end; `TruncatedPath` keeps the last path segment
// visible and clips the front part (a path is most useful at its end).
// This is the table convention (.agents/frontend.md §6): every cell whose
// content can be long uses one of these, so rows keep a uniform height.
import * as React from "react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface BaseProps {
  /** Full text, shown in the tooltip when the cell clips it. */
  text: string;
  className?: string;
  /** Mono face, for ids, URLs and paths. */
  mono?: boolean;
}

interface TextProps extends BaseProps {
  /** Wrap onto this many lines before the ellipsis (default 1: a single line). */
  lines?: 2;
  /** The clipped content when it is more than `text` (a sentence with a mono name in it); `text` is still the tooltip. */
  children?: React.ReactNode;
}

/** Wraps `children` so the tooltip opens only if `probe` finds clipped text. */
function ClipTooltip({
  text,
  isClipped,
  children,
}: {
  text: string;
  isClipped: () => boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    // Its own provider: a table cell must not depend on one being mounted above it.
    <TooltipProvider>
      <Tooltip open={open} onOpenChange={(next) => setOpen(next && isClipped())}>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent className="max-w-[420px] break-all">{text}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function TruncatedText({ text, className, mono, lines, children }: TextProps) {
  const ref = React.useRef<HTMLSpanElement>(null);
  return (
    <ClipTooltip
      text={text}
      isClipped={() => {
        const el = ref.current;
        if (!el) return false;
        return lines ? el.scrollHeight > el.clientHeight : el.scrollWidth > el.clientWidth;
      }}
    >
      <span
        ref={ref}
        data-truncated-text=""
        className={cn(
          "block min-w-0 max-w-full",
          lines ? "line-clamp-2 break-words" : "truncate",
          mono && "font-mono",
          className,
        )}
      >
        {children ?? text}
      </span>
    </ClipTooltip>
  );
}

/** Split a path into the clipped head and the last segment that stays visible. */
export function splitPath(path: string): { head: string; tail: string } {
  const trimmed = path.length > 1 ? path.replace(/\/+$/, "") : path;
  const cut = trimmed.lastIndexOf("/");
  if (cut < 0) return { head: "", tail: trimmed };
  return { head: trimmed.slice(0, cut + 1), tail: trimmed.slice(cut + 1) };
}

export function TruncatedPath({ text, className }: Omit<BaseProps, "mono">) {
  const ref = React.useRef<HTMLSpanElement>(null);
  const { head, tail } = splitPath(text);
  return (
    <ClipTooltip
      text={text}
      isClipped={() => {
        const box = ref.current;
        if (!box) return false;
        return Array.from(box.children).some((c) => c.scrollWidth > c.clientWidth);
      }}
    >
      <span
        ref={ref}
        data-truncated-path=""
        className={cn("flex min-w-0 max-w-full font-mono", className)}
      >
        {head ? <span className="min-w-0 shrink truncate">{head}</span> : null}
        <span className={cn("truncate", head ? "max-w-[75%] shrink-0" : "min-w-0")}>{tail}</span>
      </span>
    </ClipTooltip>
  );
}
