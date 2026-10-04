// src/components/agents/mcp/useOwnMcpBulk.tsx — bulk Adopt and Remove over the agent's own MCP entries.
//
// Spec agent-registry "Act on several of an agent's own items at once". The bar
// offers Adopt (entries that bypass Coffer only: a duplicate is removed, not
// adopted) with each entry's default name and default secret references, and
// Remove… (every ticked entry; an entry of an unreadable file takes no
// checkbox). Each is the single-entry request, sent one after another; a name
// Coffer already has fails that entry alone.
import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { BulkFailures } from "@/components/agents/bulk/BulkFailures";
import { useBulkDialog } from "@/components/agents/bulk/useBulkDialog";
import { buildAdoptBody, defaultSecretRefs } from "@/components/agents/mcp/adoptBody";
import type { OwnMcpRow } from "@/components/agents/mcp/mcpRows";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { agentsApi } from "@/lib/api/agents";
import { agentMcpEntriesKey, resourcesByKindKey } from "@/lib/api/queryKeys";
import { joinNames } from "@/lib/skills/names";

type Kind = "adopt" | "remove";

interface Options {
  agentUid: string;
  /** The agent's fixed name, which the minted secret references spell. */
  agentName: string;
  agentLabel: string;
  /** The file an entry sits in, home-relative. */
  whereLabel: (source: string) => string;
}

export function useOwnMcpBulk({ agentUid, agentName, agentLabel, whereLabel }: Options) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const invalidate = useMemo(
    () => [agentMcpEntriesKey(agentUid), resourcesByKindKey("mcp_server")],
    [agentUid],
  );
  const dialog = useBulkDialog<OwnMcpRow>(invalidate);
  const [kind, setKind] = useState<Kind>("adopt");
  const [skipped, setSkipped] = useState(0);

  const open = (next: Kind, rows: OwnMcpRow[], clear: () => void) => {
    const applicable = next === "adopt" ? rows.filter((r) => r.state === "bypasses") : rows;
    setKind(next);
    setSkipped(rows.length - applicable.length);
    dialog.start(applicable, clear);
  };

  const actions = (rows: OwnMcpRow[], clear: () => void): ReactNode => {
    const adoptable = rows.filter((r) => r.state === "bypasses").length;
    return (
      <>
        <Button
          variant="outline"
          size="sm"
          disabled={adoptable === 0}
          title={adoptable === 0 ? t("agents.mcpTab.bulk.adoptDisabled") : undefined}
          onClick={() => open("adopt", rows, clear)}
        >
          {t("agents.mcpTab.adopt")}
        </Button>
        <Button variant="outline" size="sm" onClick={() => open("remove", rows, clear)}>
          <Trash2 aria-hidden /> {t("agents.mcpTab.bulk.remove")}
        </Button>
      </>
    );
  };

  const items = dialog.items ?? [];
  const total = items.length;
  const failed = dialog.failures.length;
  const adopt = kind === "adopt";
  const secrets = items.reduce((sum, row) => sum + row.entry.secret_keys.length, 0);
  const names = joinNames(
    items.map((r) => r.name),
    i18n.language,
  );

  const confirm = () =>
    void dialog.confirm(
      (row) =>
        adopt
          ? agentsApi.adoptMcpEntry(
              agentUid,
              row.name,
              buildAdoptBody(row.entry, defaultSecretRefs(agentName, row.entry), ""),
            )
          : agentsApi.removeMcpEntry(agentUid, row.name, row.entry.source),
      (count) =>
        toast.success(
          t(adopt ? "agents.mcpTab.bulk.adopted" : "agents.mcpTab.bulk.removed", { count }),
        ),
    );

  const dialogs = (
    <ConfirmDialog
      open={dialog.items !== null}
      onOpenChange={(next) => {
        if (!next) dialog.close();
      }}
      title={t(adopt ? "agents.mcpTab.bulk.adoptTitle" : "agents.mcpTab.bulk.removeTitle", {
        count: total,
      })}
      description={
        adopt
          ? t("agents.mcpTab.bulk.adoptBody", { count: total, names })
          : t("agents.mcpTab.bulk.removeBody", { agent: agentLabel })
      }
      variant={adopt ? "default" : "destructive"}
      confirmLabel={
        failed > 0
          ? t("agents.mcpTab.bulk.retry", { count: failed })
          : t(adopt ? "agents.mcpTab.bulk.adoptConfirm" : "agents.mcpTab.bulk.removeConfirm", {
              count: total,
            })
      }
      pendingLabel={t(adopt ? "agents.mcpTab.adoptDialog.pending" : "agents.mcpTab.bulk.removing")}
      pending={dialog.isPending}
      onConfirm={confirm}
    >
      {adopt && secrets > 0 ? (
        <p className="text-xs text-text-muted">
          {t("agents.mcpTab.bulk.secrets", { count: secrets })}
        </p>
      ) : null}
      {!adopt ? (
        <ul className="flex max-h-40 flex-col gap-0.5 overflow-y-auto text-xs text-text-muted">
          {items.map((row) => (
            <li key={row.key} className="break-all">
              <span className="font-mono text-text">{row.name}</span>
              {" — "}
              <span className="font-mono">{whereLabel(row.entry.source)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {skipped > 0 ? (
        <p className="text-xs text-text-muted">
          {t("agents.mcpTab.bulk.skipped", { count: skipped })}
        </p>
      ) : null}
      {failed > 0 ? (
        <BulkFailures
          title={t(adopt ? "agents.mcpTab.bulk.adoptPartial" : "agents.mcpTab.bulk.removePartial", {
            ok: total - failed,
            total,
          })}
          failures={dialog.failures}
          nameOf={(row) => row.name}
        />
      ) : null}
    </ConfirmDialog>
  );

  return { actions, dialogs };
}
