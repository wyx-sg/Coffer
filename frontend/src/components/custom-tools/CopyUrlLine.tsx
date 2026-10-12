// src/components/custom-tools/CopyUrlLine.tsx — a request's method chip and URL with Copy, as a test result and the
// Test tab's request show it. `wrap` breaks a long URL over lines instead of cutting it short.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MethodChip } from "./MethodChip";

export function CopyUrlLine({
  method,
  url,
  wrap = false,
}: {
  method: string;
  url: string;
  wrap?: boolean;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <p className="flex min-w-0 items-start gap-2">
      <MethodChip method={method} className="mt-px" />
      <span
        className={cn(
          "min-w-0 flex-1 font-mono text-xs",
          wrap ? "break-all text-text" : "truncate text-text-muted",
        )}
        title={url}
      >
        {url}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={t("common.copy")}
        className="-my-0.5 text-text-subtle"
        onClick={() =>
          void navigator.clipboard?.writeText(url).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          })
        }
      >
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      </Button>
    </p>
  );
}
