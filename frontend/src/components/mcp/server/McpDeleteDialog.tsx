// src/components/mcp/server/McpDeleteDialog.tsx — Delete <name>? with what it costs (design 4.1.19; 420 wide).
//
// Says who loses how many tools and that its call history stays in Activity.
// A secret only this server cites can go with it — an unticked box, "Also
// delete the secret <NAME>", so a delete never takes a credential by surprise;
// one other things use is never offered. It closes only when the delete
// succeeded (ConfirmDialog); a refusal stays in the dialog under "Couldn’t
// delete <name>".
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/api/resources";
import { useDeleteSecret, useSecrets } from "@/lib/hooks/useSecrets";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { SecretName } from "@/components/secret/SecretNameLink";

interface Props {
  resource: ResourceOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The agents that lose its tools, already worded. */
  agentNames: string;
  toolCount: number;
  onDeleted: () => void;
}

function citedRefs(config: unknown): string[] {
  const refs = (config as { transport?: { secret_refs?: Record<string, string> } } | null)
    ?.transport?.secret_refs;
  return refs ? [...new Set(Object.values(refs))] : [];
}

export function McpDeleteDialog({
  resource,
  open,
  onOpenChange,
  agentNames,
  toolCount,
  onDeleted,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const del = useDeleteResource();
  const delSecret = useDeleteSecret();
  const secrets = useSecrets(open);
  const [alsoDelete, setAlsoDelete] = useState<ReadonlySet<string>>(new Set());

  // Secrets only this server cites: the others stay with whatever else uses them.
  const own = citedRefs(resource.config).filter((ref) => {
    const row = secrets.data?.refs.find((r) => r.ref === ref);
    return !!row && row.cited_by.length > 0 && row.cited_by.every((c) => c.uid === resource.uid);
  });
  const tools =
    toolCount > 0 ? t("mcp.page.itsTools", { count: toolCount }) : t("mcp.page.itsToolsAny");

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) {
          del.reset();
          setAlsoDelete(new Set());
        }
      }}
      title={t("mcp.page.delete.title", { name: resource.name })}
      description={
        agentNames
          ? t("mcp.page.delete.body", { agents: agentNames, tools })
          : t("mcp.page.delete.bodyNone")
      }
      confirmLabel={t("mcp.page.delete.confirm")}
      confirmIcon={<Trash2 aria-hidden />}
      pendingLabel={t("common.deleting")}
      errorTitle={t("common.couldntDelete", { name: resource.name })}
      pending={del.isPending}
      error={del.error}
      onConfirm={() =>
        del.mutate(
          { kind: "mcp_server", uid: resource.uid },
          {
            onSuccess: () => {
              for (const ref of alsoDelete)
                delSecret.mutate(ref, {
                  onError: (err) => toast.error(translateApiError(t, err)),
                });
              onOpenChange(false);
              onDeleted();
            },
          },
        )
      }
    >
      {own.map((ref) => (
        <label key={ref} className="flex items-start gap-2.5 text-sm text-text">
          <Checkbox
            className="mt-0.5"
            checked={alsoDelete.has(ref)}
            onChange={(e) =>
              setAlsoDelete((prev) => {
                const next = new Set(prev);
                if (e.target.checked) next.add(ref);
                else next.delete(ref);
                return next;
              })
            }
          />
          <span className="flex flex-col gap-0.5">
            <span>
              {t("mcp.page.delete.alsoSecret")}{" "}
              <span className="text-xs font-label">
                <SecretName secretRef={ref} />
              </span>
            </span>
            <span className="text-xs text-text-muted">{t("mcp.page.delete.secretOnlyHere")}</span>
          </span>
        </label>
      ))}
      <p className="text-xs text-text-muted">{t("mcp.page.delete.footnote")}</p>
    </ConfirmDialog>
  );
}
