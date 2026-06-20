import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { getApiClient } from "@/lib/api/client";
import { translateApiError, throwApiError } from "@/lib/api/errors";
import { JsonImportPanel } from "./JsonImportPanel";
import type { ParsedServer } from "./jsonImport";

interface ServerPlan {
  config: Record<string, unknown>;
  secrets: { ref: string; value: string }[];
}

/**
 * Turn a parsed JSON server into a Coffer config plus the list of
 * credential writes to perform. Pure (no network) — so the config is fully
 * built before any side effect runs. Secret env vars become
 * `credential_refs`; non-secret values stay inline — in `env` for stdio,
 * in `headers` for http (HttpTransport has no `env` field), mirroring how
 * the secret path already routes to each transport's credential_refs.
 */
function planServer(srv: ParsedServer): ServerPlan {
  const credentialRefs: Record<string, string> = {};
  const plain: Record<string, string> = {};
  const secrets: { ref: string; value: string }[] = [];
  for (const e of srv.env) {
    if (e.isSecret) {
      const ref = `${srv.name}.${e.key}`;
      credentialRefs[e.key] = ref;
      secrets.push({ ref, value: e.value });
    } else {
      plain[e.key] = e.value;
    }
  }
  const transport =
    srv.transportType === "stdio"
      ? {
          type: "stdio",
          command: srv.command,
          args: srv.args,
          env: plain,
          credential_refs: credentialRefs,
        }
      : { type: "http", url: srv.url, headers: plain, credential_refs: credentialRefs };
  return { config: { transport, auto_enable_new_capabilities: true }, secrets };
}

async function registerResource(name: string, config: Record<string, unknown>): Promise<void> {
  const client = getApiClient();
  const { error } = await client.POST("/resources", {
    body: { kind: "mcp_server", name, config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "register failed");
}

async function writeCredential(ref: string, value: string): Promise<void> {
  const client = getApiClient();
  const { error } = await client.POST("/credentials", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "credential write failed");
}

/**
 * Best-effort rollback of a just-registered resource whose secret writes
 * failed. We try to leave nothing behind referencing a credential that
 * was never stored; any cleanup error is logged but not surfaced — the
 * primary failure (the secret write) is what the user needs to act on.
 */
async function rollbackResource(name: string): Promise<void> {
  try {
    const client = getApiClient();
    await client.DELETE("/resources/{kind}/{name}", {
      params: { path: { kind: "mcp_server", name } },
    });
  } catch (e) {
    console.warn(`[AddMcpServerDialog] rollback delete failed for ${name}:`, e);
  }
}

/**
 * "Add MCP server" modal — paste the standard `mcpServers` JSON, review
 * which env values are secrets, and import a batch. Each server is
 * registered before its secrets are written to the encrypted credential
 * store, so a failed registration leaves nothing orphaned.
 */
export function AddMcpServerDialog() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  // Names already registered in a prior attempt of THIS import session, so a
  // retry after a partial failure re-attempts only the servers that failed
  // instead of re-POSTing the created ones (which would 409 "already exists").
  const createdRef = useRef<Set<string>>(new Set());

  const importBatch = useMutation({
    mutationFn: async (servers: ParsedServer[]) => {
      const created: string[] = [];
      const failed: string[] = [];
      for (const srv of servers) {
        if (createdRef.current.has(srv.name)) {
          created.push(srv.name);
          continue;
        }
        const { config, secrets } = planServer(srv);
        let registered = false;
        try {
          // Register first, then write to the encrypted credential store —
          // a failed registration leaves no orphaned credential entries.
          await registerResource(srv.name, config);
          registered = true;
          for (const s of secrets) {
            await writeCredential(s.ref, s.value);
          }
          createdRef.current.add(srv.name);
          created.push(srv.name);
        } catch (e) {
          // Secret write failed after registration — roll the resource
          // back so we don't leave a Coffer server pointing at a
          // credential ref that was never stored in the encrypted store.
          if (registered) {
            await rollbackResource(srv.name);
          }
          failed.push(`${srv.name}: ${translateApiError(t, e)}`);
        }
      }
      // A partial failure keeps the servers that did register; the
      // summary names every one that failed.
      if (failed.length > 0) throw new Error(failed.join("; "));
      return created;
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
    },
    onSuccess: (created) => {
      setOpen(false);
      if (created.length === 1) {
        navigate(`/mcp-servers/mcp_server/${created[0]}`);
      }
    },
    onError: (err: unknown) => {
      setServerError(err instanceof Error ? err.message : String(err));
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) createdRef.current = new Set();
        else setServerError(null);
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-1 size-4" /> {t("resources.addServer")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("mcp.server.addTitle")}</DialogTitle>
          <DialogDescription>{t("mcp.server.addSubtitle")}</DialogDescription>
        </DialogHeader>
        {serverError ? (
          <div
            className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            {serverError}
          </div>
        ) : null}
        <JsonImportPanel
          onImport={(servers) => {
            setServerError(null);
            importBatch.mutate(servers);
          }}
          importing={importBatch.isPending}
        />
      </DialogContent>
    </Dialog>
  );
}
