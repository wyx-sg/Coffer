// src/components/custom-tools/DefinitionRow.tsx — one read-only row of a definition: a fixed label column,
// the value on one line (ellipsis, the full value on hover), a copy button, and an optional trailing slot.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  /** The full value: what the tooltip shows and the copy button copies. */
  value: string;
  /** Renders in place of `value` (the value still drives tooltip and copy). */
  children?: ReactNode;
  mono?: boolean;
  /** Offer a copy button (default: yes). */
  copyable?: boolean;
  /** After the value: a badge, a button. */
  trailing?: ReactNode;
}

export function DefinitionRow({
  label,
  value,
  children,
  mono = false,
  copyable = true,
  trailing,
}: Props) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="group flex min-h-row items-center gap-3 border-b border-border-subtle last:border-b-0">
      <span className="w-32 shrink-0 text-xs text-text-muted">{label}</span>
      <TooltipProvider delayDuration={400}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={cn("min-w-0 truncate text-sm", mono && "font-mono text-xs")}>
              {children ?? value}
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-md break-all font-mono text-xs">{value}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      {copyable ? (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={t("common.copy")}
          className="text-text-muted"
          onClick={copy}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        </Button>
      ) : null}
      {trailing}
    </div>
  );
}
