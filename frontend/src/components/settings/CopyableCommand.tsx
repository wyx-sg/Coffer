// src/components/settings/CopyableCommand.tsx — a shell command shown to copy (Settings › Daemon's restart in a browser, the launcher install line).
import { Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

interface Props {
  command: string;
}

/** `$ <command>` in mono with a Copy button beside it. */
export function CopyableCommand({ command }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      toast.success(t("common.copied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md border border-border-subtle bg-surface-sunken py-1 pl-3 pr-1">
      <code className="min-w-0 flex-1 truncate font-mono text-xs text-text">
        <span className="select-none text-text-subtle">$ </span>
        {command}
      </code>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => void copy()}
        aria-label={t("settings.daemonTab.copyCommand", { command })}
      >
        <Copy aria-hidden /> {t("common.copy")}
      </Button>
    </div>
  );
}
