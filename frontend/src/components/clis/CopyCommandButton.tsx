// src/components/clis/CopyCommandButton.tsx — an icon button that copies one command line (`git commit`) to the clipboard.
import { Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

interface Props {
  /** The full command line to copy. */
  line: string;
}

export function CopyCommandButton({ line }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(line);
      toast.success(t("common.copied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      aria-label={t("clis.commands.copyLine", { line })}
      onClick={(e) => {
        e.stopPropagation();
        void copy();
      }}
    >
      <Copy aria-hidden />
    </Button>
  );
}
