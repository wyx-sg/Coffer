// src/components/mcp/server/McpDeleteDialog.tsx — Delete <name>? with what it costs, and the secrets only it uses (design 4.1.12).
//
// Says which agents lose its tools on their next call and that its call
// history stays in Activity; offers deleting each secret this server cites
// that no other resource does (deleted only once the server is gone, since a
// secret still cited is refused); and points to Turn off for a pause. It
// closes only when the delete succeeded (ConfirmDialog), keeping its error.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { secretsApi } from "@/lib/api/secret";
import type { ResourceOut } from "@/lib/api/resources";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { secretLabel } from "./serverState";

interface Props {
  resource: ResourceOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The agents that lose its tools, already worded. */
  agentNames: string;
  /** How many agents those are (the sentence reads "Both agents…" for two). */
  agentCount: number;
  toolCount: number;
  onDeleted: () => void;
}

function citedRefs(config: unknown): string[] {
  const refs = (config as { transport?: { secret_refs?: Record<string, string> } } | null)
    ?.transport?.secret_refs;
  return refs ? Object.values(refs) : [];
}

export function McpDeleteDialog({
  resource,
  open,
  onOpenChange,
  agentNames,
  agentCount,
  toolCount,
  onDeleted,
}: Props) {
  const { t } = useTranslation();
  const del = useDeleteResource();
  const secrets = useSecrets();
  const [dropSecrets, setDropSecrets] = useState(false);

  const mine = new Set(citedRefs(resource.config));
  const onlyMine = (secrets.data?.refs ?? []).filter(
    (r) => mine.has(r.ref) && r.present && r.cited_by.every((c) => c.uid === resource.uid),
  );

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) del.reset();
      }}
      title={t("mcp.page.delete.title", { name: resource.name })}
      description={
        agentNames
          ? t(
              agentCount === 1
                ? "mcp.page.delete.bodyOne"
                : agentCount === 2
                  ? "mcp.page.delete.bodyBoth"
                  : "mcp.page.delete.bodyMany",
              {
                agents: agentNames,
                agentCount,
                tools:
                  toolCount > 0
                    ? t("mcp.page.itsTools", { count: toolCount })
                    : t("mcp.page.itsToolsAny"),
              },
            )
          : t("mcp.page.delete.bodyNoAgents")
      }
      confirmLabel={del.isPending ? t("common.deleting") : t("mcp.page.delete.confirm")}
      pending={del.isPending}
      error={del.error}
      onConfirm={() =>
        del.mutate(
          { kind: "mcp_server", uid: resource.uid },
          {
            onSuccess: () => {
              if (dropSecrets) {
                // Best-effort: the server is gone either way; a secret that
                // cannot go stays on the Secrets page.
                for (const s of onlyMine) void secretsApi.remove(s.ref).catch(() => undefined);
              }
              onOpenChange(false);
              onDeleted();
            },
          },
        )
      }
    >
      {onlyMine.length > 0 ? (
        <label className="flex items-start gap-2 text-sm">
          <Checkbox checked={dropSecrets} onChange={(e) => setDropSecrets(e.target.checked)} />
          <span className="flex flex-col">
            <span>
              {t("mcp.page.delete.alsoSecrets", { count: onlyMine.length })}{" "}
              <span className="font-mono">
                {onlyMine.map((s) => secretLabel(s.ref)).join(", ")}
              </span>
            </span>
            <span className="text-xs text-text-muted">{t("mcp.page.delete.noOtherUser")}</span>
          </span>
        </label>
      ) : null}
      <p className="text-xs text-text-muted">{t("mcp.page.delete.pause")}</p>
    </ConfirmDialog>
  );
}
