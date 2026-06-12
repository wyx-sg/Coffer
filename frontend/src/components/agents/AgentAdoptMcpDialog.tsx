// frontend/src/components/agents/AgentAdoptMcpDialog.tsx
// "Adopt into Coffer" dialog for a direct MCP entry (specs 004/005 workspace amendment). Shows a short
// summary of the entry, and — when the entry carries likely-secret env/header
// keys — one input per secret key so the user can choose the keychain
// reference each value is stored under (prefilled mcp/{agent}/{entry}/{KEY});
// the secret VALUES never travel through this form, the daemon moves them
// into the system keychain. A rename field stays hidden until the daemon
// answers 409 name-conflict with a `suggested_name`, then the resubmit
// carries `new_name`.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import type { AdoptMcpEntryBody, McpEntryOut } from "@/lib/api/agents";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useAdoptMcpEntry } from "@/lib/hooks/useAgents";

function defaultSecretRefs(agentName: string, entry: McpEntryOut): Record<string, string> {
  return Object.fromEntries(
    entry.secret_keys.map((key) => [key, `mcp/${agentName}/${entry.name}/${key}`]),
  );
}

export function AgentAdoptMcpDialog({
  agentName,
  entry,
  open,
  onOpenChange,
}: {
  agentName: string;
  entry: McpEntryOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const adopt = useAdoptMcpEntry(agentName);

  const [secrets, setSecrets] = useState<Record<string, string>>(() =>
    defaultSecretRefs(agentName, entry),
  );
  // Hidden until the daemon reports a 409 name conflict with a suggestion.
  const [showRename, setShowRename] = useState(false);
  const [newName, setNewName] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Fresh form whenever the dialog (re)opens or targets a different entry.
  useEffect(() => {
    if (open) {
      setSecrets(defaultSecretRefs(agentName, entry));
      setShowRename(false);
      setNewName("");
      setErrorMsg(null);
    }
  }, [open, agentName, entry]);

  const submit = () => {
    const body: AdoptMcpEntryBody = { source: entry.source };
    if (entry.secret_keys.length > 0) body.secrets = secrets;
    if (showRename && newName.trim()) body.new_name = newName.trim();
    adopt.mutate(
      { entry: entry.name, body },
      {
        onSuccess: (res) => {
          toast.success(t("agents.workspace.mcp.adoptSuccess", { name: res.name }));
          onOpenChange(false);
        },
        onError: (err) => {
          const details =
            err instanceof ApiError
              ? (err.details as { suggested_name?: string } | undefined)
              : undefined;
          if (details?.suggested_name) {
            // 409 name conflict → reveal the rename field, prefilled with the
            // daemon's suggestion; resubmitting sends `new_name`.
            setShowRename(true);
            setNewName(details.suggested_name);
            setErrorMsg(t("agents.workspace.mcp.adoptRename"));
            return;
          }
          // Includes 422 ADOPT_SECRET_UNRESOLVED — show the daemon's message.
          setErrorMsg(translateApiError(t, err));
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("agents.workspace.mcp.adoptTitle")}</DialogTitle>
          <DialogDescription asChild>
            <span className="flex items-center gap-2">
              <span className="font-medium text-foreground">{entry.name}</span>
              <Badge variant="outline">{entry.transport}</Badge>
              <span className="line-clamp-1 font-mono text-xs">
                {entry.transport === "stdio"
                  ? [entry.command, ...entry.args].filter(Boolean).join(" ")
                  : (entry.url ?? "")}
              </span>
            </span>
          </DialogDescription>
        </DialogHeader>

        {entry.secret_keys.length > 0 && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {t("agents.workspace.mcp.adoptSecretsHint")}
            </p>
            {entry.secret_keys.map((key) => (
              <div key={key} className="space-y-1.5">
                <Label htmlFor={`adopt-secret-${key}`}>{key}</Label>
                <Input
                  id={`adopt-secret-${key}`}
                  value={secrets[key] ?? ""}
                  onChange={(e) => setSecrets((prev) => ({ ...prev, [key]: e.target.value }))}
                  className="font-mono text-xs"
                />
              </div>
            ))}
          </div>
        )}

        {showRename && (
          <div className="space-y-1.5">
            <Label htmlFor="adopt-new-name">{t("agents.name")}</Label>
            <Input
              id="adopt-new-name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
          </div>
        )}

        {errorMsg && (
          <Alert variant="destructive">
            <AlertDescription>{errorMsg}</AlertDescription>
          </Alert>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={adopt.isPending} onClick={submit}>
            {t("agents.workspace.mcp.adopt")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
