// frontend/src/components/mcp/AddMcpServerDialog.tsx
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
import { BatchImportError } from "./importMcpServers";
import { JsonImportPanel } from "./JsonImportPanel";

/**
 * "Add MCP server" modal — paste the standard `mcpServers` JSON, review
 * which env values are secrets, and import a batch (importMcpServers.ts
 * does the registering and rolling back). A partial failure keeps the
 * servers that did register and lists every one that did not, one line each.
 */
export function AddMcpServerDialog() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  // What a prior attempt of THIS import session already registered — name to
  // uid — so a retry after a partial failure re-attempts only the servers that
  // failed instead of re-POSTing the created ones (which would 409 "already
  // exists"), and so a retry that ends with one server still knows where it is.
  const createdRef = useRef<Map<string, string>>(new Map());
  const importBatch = useImportMcpServers();

  const runImport = (servers: ParsedServer[]) => {
    setServerErrors([]);
    importBatch.mutate(
      { servers, created: createdRef.current },
      {
        onSuccess: (created) => {
          setOpen(false);
          if (created.length === 1) {
            navigate(`/mcp-servers/${encodeURIComponent(created[0].uid)}`);
          }
        },
        onError: (err: unknown) => {
          setServerErrors(
            err instanceof BatchImportError
              ? err.failed
              : [err instanceof Error ? err.message : String(err)],
          );
        },
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) createdRef.current = new Map();
        else setServerErrors([]);
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
        {serverErrors.length > 0 ? (
          <ul
            className="list-inside list-disc space-y-1 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            {serverErrors.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
        <JsonImportPanel onImport={runImport} importing={importBatch.isPending} />
      </DialogContent>
    </Dialog>
  );
}
