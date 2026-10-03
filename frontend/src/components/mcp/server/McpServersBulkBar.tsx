// src/components/mcp/server/McpServersBulkBar.tsx — the MCP servers list's selection bar, in the place of the search while rows are ticked (design 4.1.28).
//
// "N of M selected · Reach ▾ · Delete · ×" (Esc clears too): the selection's reach — the same
// three-way choice the server's header carries (spec web-ui "Mount one reach
// control in three places") — a red outline Delete with its confirmation, and
// a × that clears the selection. The built-in `coffer` server has no checkbox,
// so it is never in it.
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { ResourceOut } from "@/lib/api/resources";
import { useBulkDeleteResources } from "@/lib/hooks/useResourceMutations";

interface Props {
  servers: ResourceOut[];
  /** How many servers the search shows: the "of M". */
  total: number;
  onDone: () => void;
}

export function McpServersBulkBar({ servers, total, onDone }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkDeleteResources();
  const [confirming, setConfirming] = useState(false);
  // Esc clears the selection, unless a dialog or menu is open over the page.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"]')) return;
      onDone();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onDone]);
  return (
    <div
      role="region"
      aria-label={t("mcp.page.bulkLabel")}
      className="flex h-[38px] items-center gap-1.5 rounded-lg bg-surface-sunken pl-2.5 pr-1.5"
    >
      <span className="mr-auto whitespace-nowrap text-xs font-semibold text-text">
        {t("common.bulk.selectedOf", { count: servers.length, total })}
      </span>
      <BulkReachActions
        rows={servers.map((s) => ({
          kind: "mcp_server",
          uid: s.uid,
          name: s.name,
          enabled: s.enabled,
          scope: s.scope,
        }))}
        onDone={onDone}
      />
      <Button
        size="sm"
        variant="danger"
        disabled={bulk.isPending}
        onClick={() => setConfirming(true)}
      >
        {t("common.bulk.delete")}
      </Button>
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label={t("mcp.page.clearSelection")}
        onClick={onDone}
      >
        <X aria-hidden />
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("mcp.page.deleteManyTitle", { count: servers.length })}
        description={t("mcp.page.deleteManyBody")}
        confirmLabel={t("common.bulk.delete")}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteSelected")}
        pending={bulk.isPending}
        onConfirm={async () => {
          await bulk.run(servers);
          onDone();
        }}
      />
    </div>
  );
}
