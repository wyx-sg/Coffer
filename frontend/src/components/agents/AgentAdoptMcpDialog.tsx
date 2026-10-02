// src/components/agents/AgentAdoptMcpDialog.tsx — adopt one direct MCP entry into Coffer (boards 2.1.24, 2.1.25).
//
// Spec agent-registry "Adopt a direct MCP entry into Coffer". The dialog says
// what will happen — Coffer serves the server to every agent and then takes
// the entry out of the agent's file, keeping a .bak — and shows the name it
// will have in Coffer, the command, and every env / header key with how it will
// be stored. A secret-looking key's value moves into the encrypted vault under
// a secret reference (prefilled `mcp/{agent}/{entry}/{KEY}`: an address a
// person reads, minted once, never looked up by name); the value never travels
// through this form. A name already taken in Coffer is said under the name
// field (409 name conflict) and the user renames and retries; any other failure
// is shown inline. The primary button reads "Adopting…" while it runs.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AdoptKeyTable } from "@/components/agents/mcp/AdoptKeyTable";
import { entryCommand } from "@/components/agents/mcp/mcpRows";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import type { AdoptedResource, AdoptMcpEntryBody, McpEntryOut } from "@/lib/api/agents-workspace";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useAdoptMcpEntry } from "@/lib/hooks/useAgents";

function defaultSecretRefs(agentName: string, entry: McpEntryOut): Record<string, string> {
  return Object.fromEntries(
    entry.secret_keys.map((key) => [key, `mcp/${agentName}/${entry.name}/${key}`]),
  );
}

/** The daemon's 409: the name is taken in Coffer (it sends a `suggested_name`). */
function isNameConflict(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  const details = err.details as { suggested_name?: string } | undefined;
  return Boolean(details?.suggested_name) || err.code.endsWith("ALREADY_EXISTS");
}

interface Props {
  /** The agent being adopted from — what the adopt request is addressed to. */
  agentUid: string;
  /** Its fixed name, which the minted secret refs spell. */
  agentName: string;
  /** Its product name, for the sentences ("so Claude Code never gets it twice"). */
  agentLabel: string;
  /** The file the entry sits in, home-relative. */
  fileLabel: string;
  entry: McpEntryOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with what adoption created, after the dialog closes. */
  onAdopted?: (created: AdoptedResource) => void;
}

export function AgentAdoptMcpDialog({
  agentUid,
  agentName,
  agentLabel,
  fileLabel,
  entry,
  open,
  onOpenChange,
  onAdopted,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const adopt = useAdoptMcpEntry(agentUid);
  const [refs, setRefs] = useState(() => defaultSecretRefs(agentName, entry));
  const [name, setName] = useState(entry.name);
  const [conflict, setConflict] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // A fresh form whenever the dialog opens or targets another entry.
  useEffect(() => {
    if (!open) return;
    setRefs(defaultSecretRefs(agentName, entry));
    setName(entry.name);
    setConflict(null);
    setErrorMsg(null);
  }, [open, agentName, entry]);

  const secret = new Set(entry.secret_keys);
  const trimmed = name.trim();

  const submit = () => {
    const body: AdoptMcpEntryBody = { source: entry.source };
    if (entry.secret_keys.length > 0) body.secrets = refs;
    if (trimmed && trimmed !== entry.name) body.new_name = trimmed;
    setConflict(null);
    setErrorMsg(null);
    adopt.mutate(
      { entry: entry.name, body },
      {
        onSuccess: (res) => {
          toast.success(t("agents.mcpTab.adoptDialog.success", { name: res.name }));
          onOpenChange(false);
          onAdopted?.(res);
        },
        onError: (err) => {
          if (isNameConflict(err)) setConflict(trimmed || entry.name);
          else setErrorMsg(translateApiError(t, err));
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("agents.mcpTab.adoptDialog.title", { name: entry.name })}</DialogTitle>
          <DialogDescription>
            {t("agents.mcpTab.adoptDialog.description", { file: fileLabel })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="adopt-mcp-name" required>
              {t("agents.mcpTab.adoptDialog.name")}
            </Label>
            <Input
              id="adopt-mcp-name"
              value={name}
              aria-invalid={conflict !== null || undefined}
              onChange={(e) => setName(e.target.value)}
            />
            {conflict !== null ? (
              <p className="text-xs text-destructive" role="alert">
                {t("agents.mcpTab.adoptDialog.nameConflict", { name: conflict })}
              </p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <p className="text-xs font-label text-text">
              {entry.transport === "stdio"
                ? t("agents.mcpTab.adoptDialog.command")
                : t("agents.mcpTab.adoptDialog.url")}
            </p>
            <p className="break-all rounded-md bg-surface-sunken px-3 py-2 font-mono text-xs text-text">
              {entryCommand(entry)}
            </p>
          </div>

          {entry.env_keys.length > 0 ? (
            <AdoptKeyTable
              title={t("agents.mcpTab.adoptDialog.env")}
              keys={entry.env_keys}
              secret={secret}
              refs={refs}
              onRefChange={(key, ref) => setRefs((prev) => ({ ...prev, [key]: ref }))}
            />
          ) : null}
          {entry.header_keys.length > 0 ? (
            <AdoptKeyTable
              title={t("agents.mcpTab.adoptDialog.headers")}
              keys={entry.header_keys}
              secret={secret}
              refs={refs}
              onRefChange={(key, ref) => setRefs((prev) => ({ ...prev, [key]: ref }))}
            />
          ) : null}

          {entry.secret_keys.length > 0 ? (
            <p className="text-xs text-text-muted">
              {t("agents.mcpTab.adoptDialog.secretNote", {
                count: entry.secret_keys.length,
                keys: entry.secret_keys.join(", "),
              })}
            </p>
          ) : null}
          <p className="text-xs text-text-muted">
            {t("agents.mcpTab.adoptDialog.leaves", { file: fileLabel, agent: agentLabel })}
          </p>

          {errorMsg ? (
            <Alert variant="error">
              <AlertDescription>{errorMsg}</AlertDescription>
            </Alert>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button loading={adopt.isPending} disabled={!trimmed} onClick={submit}>
            {adopt.isPending ? t("agents.mcpTab.adoptDialog.pending") : t("agents.mcpTab.adopt")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
