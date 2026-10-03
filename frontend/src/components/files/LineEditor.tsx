// frontend/src/components/files/LineEditor.tsx
//
// The editing surface of a document editor (boards 2.1.41, 2.1.42): the text
// in the mono face with a line-number gutter, no wrapping, on the code surface.
// One plain textarea underneath — nothing here is clever — sized to its text so
// the gutter and the lines scroll together in one scroller. A line the caller
// flags (invalid JSON) is tinted danger with its number in red and the reason
// at the line's right end.
import { CircleAlert } from "lucide-react";

import { cn } from "@/lib/utils";

// Both numbers are the textarea's line box and its padding, in px; the gutter
// and the error tint are laid out from them, so they live together.
const LINE = 20;
const PAD = 12;

export interface LineError {
  /** 1-based. */
  line: number;
  message: string;
}

export function LineEditor({
  value,
  onChange,
  ariaLabel,
  error,
  onKeyDown,
}: {
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
  error?: LineError | null;
  onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
}) {
  const lines = value.split("\n").length;
  return (
    <div className="min-h-0 flex-1 overflow-auto bg-code">
      <div className="relative flex min-h-full" style={{ minHeight: lines * LINE + PAD * 2 }}>
        <div
          aria-hidden
          style={{ paddingTop: PAD, paddingBottom: PAD }}
          className="sticky left-0 z-10 w-12 shrink-0 select-none bg-code pr-3 text-right font-mono text-2xs"
        >
          {Array.from({ length: lines }, (_, i) => (
            <div
              key={i}
              style={{ height: LINE, lineHeight: `${LINE}px` }}
              className={cn(
                error?.line === i + 1 ? "font-semibold text-danger" : "text-text-subtle",
              )}
            >
              {i + 1}
            </div>
          ))}
        </div>
        {error && error.line <= lines ? (
          <div
            aria-hidden
            style={{ top: PAD + (error.line - 1) * LINE, height: LINE }}
            className="pointer-events-none absolute inset-x-0 bg-danger-soft"
          />
        ) : null}
        <textarea
          aria-label={ariaLabel}
          aria-invalid={error ? true : undefined}
          value={value}
          spellCheck={false}
          wrap="off"
          autoCapitalize="off"
          autoCorrect="off"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          style={{ paddingTop: PAD, paddingBottom: PAD, lineHeight: `${LINE}px` }}
          className="relative min-w-0 flex-1 resize-none overflow-hidden whitespace-pre bg-transparent pr-3 font-mono text-xs text-text outline-none"
        />
        {error && error.line <= lines ? (
          <p
            role="alert"
            style={{ top: PAD + (error.line - 1) * LINE, height: LINE }}
            className="pointer-events-none absolute right-3 flex max-w-[60%] items-center gap-1.5 truncate rounded-sm bg-danger-soft pl-2 text-xs text-danger"
          >
            <CircleAlert className="size-3 shrink-0" aria-hidden />
            <span className="truncate">{error.message}</span>
          </p>
        ) : null}
      </div>
    </div>
  );
}
