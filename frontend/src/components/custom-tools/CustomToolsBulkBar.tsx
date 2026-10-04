// src/components/custom-tools/CustomToolsBulkBar.tsx — the group list's selection bar, in the place of the filter while groups are ticked.
//
// "N of M selected · Reach ▾ · Delete · ×" (Esc clears too), the same bar the MCP servers list carries: the
// selection's reach, a red Delete with its confirmation, and a × that clears the selection.
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { reachOf } from "@/lib/customTools/groups";
import { customToolsKey } from "@/lib/api/queryKeys";
import { useBulkDeleteCustomToolGroups } from "@/lib/hooks/useCustomTools";

interface Props {
  groups: CustomToolGroup[];
  /** How many groups the filter shows: the "of M". */
  total: number;
  onDone: () => void;
  /** Called with the names that were deleted, so the page can leave a deleted group's pane. */
  onDeleted: (names: string[]) => void;
}

export function CustomToolsBulkBar({ groups, total, onDone, onDeleted }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkDeleteCustomToolGroups();
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
      aria-label={t("customTools.list.bulkLabel")}
      className="flex h-[38px] items-center gap-1.5 rounded-lg bg-surface-sunken pl-2.5 pr-1.5"
    >
      <span className="mr-auto whitespace-nowrap text-xs font-semibold text-text">
        {t("common.bulk.selectedOf", { count: groups.length, total })}
      </span>
      <BulkReachActions
        rows={groups.map((g) => ({
          kind: "mcp_server",
          uid: g.uid,
          name: g.name,
          enabled: g.enabled,
          scope: reachOf(g),
        }))}
        invalidate={[customToolsKey]}
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
        aria-label={t("customTools.list.clearSelection")}
        onClick={onDone}
      >
        <X aria-hidden />
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("customTools.list.deleteManyTitle", { count: groups.length })}
        description={t("customTools.list.deleteManyBody")}
        confirmLabel={t("common.bulk.delete")}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteSelected")}
        pending={bulk.isPending}
        onConfirm={async () => {
          const deleted = await bulk.run(groups);
          onDeleted(deleted);
          onDone();
        }}
      />
    </div>
  );
}
