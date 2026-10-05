// frontend/src/components/vault/VaultHistoryDialog.tsx
// The History… dialog (spec web-ui "Show where a file's history is and hand its
// restore to an agent"): one dialog over the page for a vault file or folder —
// a knowledge document's ⋯ menu, a skill's ⋯ menu. The vault's history is git's,
// so the dialog lists no versions, shows no diff and restores nothing itself: it
// names the path in the vault, takes an optional time, copies the `git log`
// command the daemon serves, reveals the path in Finder and hands the restore
// to the person's agent with the prompt the daemon builds for that path and time.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, FolderOpen } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { vaultApi } from "@/lib/api/vault";
import { useVaultHistoryHandoff } from "@/lib/hooks/useVaultHistory";
import { useFsActions } from "@/lib/fsActions";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The vault-relative path: a file, or a folder ending in `/` (`skills/pdf/`). */
  path: string;
}

/** A `datetime-local` value as an ISO time (null while empty or incomplete). */
function toIso(local: string): string | null {
  if (!local) return null;
  const at = new Date(local);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
}

function Body({ path }: Pick<Props, "path">) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { reveal } = useFsActions();
  const [local, setLocal] = useState("");
  const at = toIso(local);
  const served = useVaultHistoryHandoff(path, at);

  const copyCommand = () => {
    if (!served.data) return;
    void navigator.clipboard.writeText(served.data.log_command).then(
      () => toast.success(t("common.copied")),
      () => toast.error(t("vaultHistory.copyFailed")),
    );
  };
  const revealPath = () => {
    if (!served.data) return;
    void reveal(served.data.absolute_path).catch(() => toast.error(t("fileActions.revealFailed")));
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("vaultHistory.title")}</DialogTitle>
        <DialogDescription>{t("vaultHistory.description")}</DialogDescription>
      </DialogHeader>
      <div className="grid gap-1.5">
        <Label>{t("vaultHistory.path")}</Label>
        <code
          data-testid="vault-history-path"
          className="break-all rounded-md bg-surface-sunken px-2.5 py-1.5 font-mono text-xs text-text"
        >
          {path}
        </code>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="vault-history-at">{t("vaultHistory.at")}</Label>
        <Input
          id="vault-history-at"
          type="datetime-local"
          value={local}
          onChange={(e) => setLocal(e.target.value)}
        />
        <p className="text-xs text-text-muted">{t("vaultHistory.atHint")}</p>
      </div>
      {served.error ? (
        <p role="alert" className="text-xs text-danger">
          {translateApiError(t, served.error)}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!served.data}
          onClick={copyCommand}
        >
          <Copy aria-hidden />
          {t("vaultHistory.copyCommand")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!served.data}
          onClick={revealPath}
        >
          <FolderOpen aria-hidden />
          {t("fileActions.reveal")}
        </Button>
      </div>
      <DialogFooter>
        <AgentHandoff
          // Asked when the verb is picked, so the prompt always names the time shown.
          prompt={async () => (await vaultApi.historyHandoff(path, at)).handoff.prompt}
          label={(agent) => t("vaultHistory.restoreWith", { agent })}
          help={false}
        />
      </DialogFooter>
    </>
  );
}

export function VaultHistoryDialog({ open, onOpenChange, path }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>{open ? <Body path={path} /> : null}</DialogContent>
    </Dialog>
  );
}
