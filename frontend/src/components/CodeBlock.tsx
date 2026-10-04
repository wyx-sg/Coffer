// frontend/src/components/CodeBlock.tsx
// A fenced code block with a Copy button; Markdown's `copyableCode` option.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";

/** How long the "Copied" confirmation stays on a code block. */
const COPIED_MS = 1500;

/** A fenced block with a Copy button (the code is what a reader most often
 *  wants out of a reply). */
export function CodeBlock({ children }: { children?: ReactNode }) {
  const { t } = useTranslation();
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    // Read the rendered text: highlighting has split the source into spans.
    const text = preRef.current?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // Clipboard unavailable (insecure context / permission denied): the
      // block stays selectable by hand.
    }
  };

  return (
    <div className="relative my-2">
      <pre
        ref={preRef}
        className="overflow-x-auto rounded-lg border border-border-subtle bg-code px-3.5 py-3 pr-12 font-mono text-xs leading-[1.6]"
      >
        {children}
      </pre>
      {copied ? (
        <span className="absolute right-10 top-2 text-xs text-muted-foreground" role="status">
          {t("common.copied")}
        </span>
      ) : null}
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="absolute right-1 top-1 text-muted-foreground hover:text-foreground"
        onClick={() => void copy()}
        aria-label={t("common.copy")}
      >
        {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      </Button>
    </div>
  );
}
