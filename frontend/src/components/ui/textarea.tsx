// src/components/ui/textarea.tsx
// The multi-line text field: the input's field look, padding 8/10, line-height 1.5, min three lines. `autoGrow`
// makes it grow with its text up to `maxRows` lines, then scroll — for text people write at length (a tool's
// description) that a fixed box would hide.
import * as React from "react";
import { cn } from "@/lib/utils";
import { fieldClass, fieldReadOnlyClass } from "@/components/ui/field-classes";

/** 13px text at line-height 1.5. */
const LINE_PX = 19.5;
/** Padding 8 + 8 and the 1px border on each side. */
const FRAME_PX = 18;

interface TextareaProps extends React.ComponentPropsWithoutRef<"textarea"> {
  autoGrow?: boolean;
  /** With `autoGrow`: the most lines it grows to (default 12). */
  maxRows?: number;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, autoGrow = false, maxRows = 12, style, ...props }, ref) => {
    const inner = React.useRef<HTMLTextAreaElement | null>(null);
    const setRefs = (node: HTMLTextAreaElement | null) => {
      inner.current = node;
      if (typeof ref === "function") ref(node);
      else if (ref) ref.current = node;
    };
    React.useLayoutEffect(() => {
      const node = inner.current;
      if (!autoGrow || !node) return;
      node.style.height = "auto";
      node.style.height = `${Math.min(node.scrollHeight + 2, maxRows * LINE_PX + FRAME_PX)}px`;
    }, [autoGrow, maxRows, props.value]);
    return (
      <textarea
        ref={setRefs}
        className={cn(
          fieldClass,
          fieldReadOnlyClass,
          // 3 lines × 19.5px + 16px padding + 2px border.
          "flex min-h-[77px] px-2.5 py-2 leading-normal caret-accent",
          autoGrow && "resize-none overflow-y-auto",
          className,
        )}
        style={style}
        {...props}
      />
    );
  },
);
Textarea.displayName = "Textarea";

export { Textarea };
