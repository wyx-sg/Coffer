// src/components/custom-tools/SpecViewer.tsx — a piece of a spec in the viewer frame (Foundations 0.6.03): a
// 40px toolbar with the mono path and a wrap toggle, then the lines with their numbers. The piece starts at
// `startLine` of the document; `mark` tints one line (where a parse failed).
import { useState } from "react";
import { WrapText } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  /** The toolbar's left side: "openapi.json · paths./invoices/{id}". */
  path: string;
  text: string;
  /** The document line `text` starts at (1-based). */
  startLine?: number;
  /** A document line to tint. */
  mark?: number;
  /** Scroll past this height (a CSS length). */
  maxHeight?: string;
  className?: string;
}

export function SpecViewer({ path, text, startLine = 1, mark, maxHeight, className }: Props) {
  const { t } = useTranslation();
  const [wrap, setWrap] = useState(false);
  const lines = text.split("\n");
  return (
    <div
      className={cn("overflow-hidden rounded-lg border border-border bg-surface-raised", className)}
    >
      <div className="flex h-10 items-center justify-between gap-2 border-b border-border-subtle px-3">
        <span className="min-w-0 truncate font-mono text-xs text-text-muted">{path}</span>
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          aria-label={t("customTools.viewer.wrap")}
          aria-pressed={wrap}
          onClick={() => setWrap(!wrap)}
        >
          <WrapText aria-hidden />
        </Button>
      </div>
      <div
        className="overflow-auto py-1 font-mono text-xs leading-5 text-text"
        style={maxHeight ? { maxHeight } : undefined}
      >
        {lines.map((line, i) => (
          <div
            key={i}
            data-line={startLine + i}
            className={cn("flex", startLine + i === mark && "bg-danger-soft")}
          >
            <span className="w-11 shrink-0 select-none pr-3 text-right text-text-subtle">
              {startLine + i}
            </span>
            <span
              className={cn(
                "min-w-0 flex-1",
                wrap ? "whitespace-pre-wrap break-all" : "whitespace-pre",
              )}
            >
              {line}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
