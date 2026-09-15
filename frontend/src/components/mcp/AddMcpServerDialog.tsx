import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import type { ParsedServer } from "./jsonImport";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useImportMcpServers } from "@/lib/hooks/useMcpServerMutations";
import { JsonImportPanel } from "./JsonImportPanel";

/**
 * "Add MCP server" modal — paste the standard `mcpServers` JSON, review
 * which env values are secrets, and import a batch (importMcpServers.ts
 * does the registering and rolling back).
 */
export function AddMcpServerDialog() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  // Names already registered in a prior attempt of THIS import session, so a
  // retry after a partial failure re-attempts only the servers that failed
  // instead of re-POSTing the created ones (which would 409 "already exists").
  const createdRef = useRef<Set<string>>(new Set());
  const importBatch = useImportMcpServers();

  const runImport = (servers: ParsedServer[]) => {
    setServerError(null);
    importBatch.mutate(
      { servers, created: createdRef.current },
      {
        onSuccess: (created) => {
          setOpen(false);
          if (created.length === 1) {
            navigate(`/mcp-servers/mcp_server/${created[0]}`);
          }
        },
        onError: (err: unknown) => {
          setServerError(err instanceof Error ? err.message : String(err));
        },
      },
    );
  };

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
        <JsonImportPanel onImport={runImport} importing={importBatch.isPending} />
      </DialogContent>
    </Dialog>
  );
}
