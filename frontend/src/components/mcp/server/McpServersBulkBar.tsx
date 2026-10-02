// src/components/mcp/server/McpServersBulkBar.tsx — the MCP servers list's selection bar, at the top of the column while rows are ticked.
//
// Select-all (every listed server the filters show; the built-in one cannot
// take a bulk action and is never in it, indeterminate when only some are
// ticked), how many are selected, Clear, the selection's reach — the same
// three-way choice the server's header carries (spec web-ui "Mount one reach
// control in three places") — and Delete.
import { useTranslation } from "react-i18next";

import { ListSelectionBar } from "@/components/ListSelectionBar";
import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import type { ResourceOut } from "@/lib/api/resources";
import { useBulkDeleteResources } from "@/lib/hooks/useResourceMutations";

interface Props {
  servers: ResourceOut[];
  /** Every selectable server the current filters show are ticked. */
  allChecked: boolean;
  onToggleAll: (on: boolean) => void;
  onDone: () => void;
}

export function McpServersBulkBar({ servers, allChecked, onToggleAll, onDone }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkDeleteResources();
  return (
    <ListSelectionBar
      label={t("mcp.page.bulkLabel")}
      selectAllLabel={t("mcp.page.selectAll")}
      count={servers.length}
      allChecked={allChecked}
      onToggleAll={onToggleAll}
      onClear={onDone}
    >
      <BulkReachActions rows={servers} onDone={onDone} />
      <BulkDeleteButton
        title={t("mcp.page.deleteManyTitle", { count: servers.length })}
        description={t("mcp.page.deleteManyBody")}
        pending={bulk.isPending}
        onConfirm={async () => {
          await bulk.run(servers);
          onDone();
        }}
      />
    </ListSelectionBar>
  );
}
