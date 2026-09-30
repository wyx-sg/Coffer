// src/components/mcp/server/McpServersBulkBar.tsx — the MCP servers list's selection bar: how many, the selection's reach, Delete them all.
//
// The reach control is the same three-way choice the server's header carries
// (spec web-ui "Mount one reach control in three places"), applied to the
// whole selection; Delete stays its own button beside it.
import { useTranslation } from "react-i18next";

import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { Button } from "@/components/ui/button";
import { resourcesKey } from "@/lib/api/queryKeys";
import { resourcesApi, type ResourceOut } from "@/lib/api/resources";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

interface Props {
  servers: ResourceOut[];
  onDone: () => void;
}

export function McpServersBulkBar({ servers, onDone }: Props) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({ invalidate: [resourcesKey] });
  return (
    <div
      role="region"
      aria-label={t("mcp.page.bulkLabel")}
      className="flex flex-wrap items-center gap-2 border-t border-border-subtle bg-surface-raised px-3 py-2"
    >
      <span className="text-xs font-label text-text">
        {t("common.bulk.selected", { count: servers.length })}
      </span>
      <Button variant="ghost" size="sm" onClick={onDone}>
        {t("common.clear")}
      </Button>
      <span className="ml-auto inline-flex flex-wrap items-center gap-2">
        <BulkReachActions rows={servers} onDone={onDone} />
        <BulkDeleteButton
          title={t("mcp.page.deleteManyTitle", { count: servers.length })}
          description={t("mcp.page.deleteManyBody")}
          pending={bulk.isPending}
          onConfirm={async () => {
            await bulk.run(servers, (r) => resourcesApi.remove(r.uid));
            onDone();
          }}
        />
      </span>
    </div>
  );
}
