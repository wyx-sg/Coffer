// src/components/mcp/server/McpDeleteDialog.tsx — Delete <name>? with what it costs (boards 1.1.10, 1.1.11).
//
// A confirmation says what the delete takes and what it leaves, in one fact
// list: the tools that disappear from the agents that reach them, and each
// secret the server cites — always kept, the Secrets page owns them. A footnote
// says past calls stay in Activity. It closes only when the delete succeeded
// (ConfirmDialog); a refusal stays in the dialog under "Couldn’t delete <name>".
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog, ConfirmFacts } from "@/components/ui/confirm-dialog";
import type { ResourceOut } from "@/lib/api/resources";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { secretLabel } from "@/lib/mcp/serverState";

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
  const del = useDeleteResource();

  const facts: { label: string; value: string }[] = [];
  if (agentNames) {
    facts.push({
      label: t("mcp.page.delete.toolsLabel"),
      value:
        toolCount > 0
          ? t("mcp.page.delete.toolsGone", { count: toolCount, agents: agentNames })
          : t("mcp.page.delete.toolsGoneAny", { agents: agentNames }),
    });
  }
  for (const ref of citedRefs(resource.config)) {
    facts.push({
      label: t("mcp.page.delete.secretLabel"),
      value: t("mcp.page.delete.secretStays", { name: secretLabel(ref) }),
    });
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) del.reset();
      }}
      title={t("mcp.page.delete.title", { name: resource.name })}
      description={t("mcp.page.delete.description")}
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
              onOpenChange(false);
              onDeleted();
            },
          },
        )
      }
    >
      {facts.length > 0 ? <ConfirmFacts items={facts} /> : null}
      <p className="text-xs text-text-subtle">{t("mcp.page.delete.footnote")}</p>
    </ConfirmDialog>
  );
}
