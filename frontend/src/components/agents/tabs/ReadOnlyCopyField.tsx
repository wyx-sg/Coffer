// src/components/agents/tabs/ReadOnlyCopyField.tsx — a read-only mono value with a Copy icon (the adopt dialogs' From and Command).
import { Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

interface Props {
  value: string;
  /** The icon button's accessible name, e.g. "Copy path". */
  copyLabel: string;
}

export function ReadOnlyCopyField({ value, copyLabel }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t("common.copied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md bg-surface-sunken py-1 pl-3 pr-1">
      <span className="min-w-0 flex-1 break-all font-mono text-xs text-text">{value}</span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={copyLabel}
        onClick={() => void copy()}
      >
        <Copy aria-hidden />
      </Button>
    </div>
  );
}
