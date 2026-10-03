// src/components/mcp/server/McpSelectionPane.tsx — the right pane while several servers are ticked: "N servers selected" and Turn off N servers (design 4.1.28).
//
// Reach and Delete live in the bar above the list; the one thing the pane adds
// is switching the whole selection off in one go.
import { Power, Server } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { ownListKeysForKind, resourcesKey } from "@/lib/api/queryKeys";
import { resourcesApi, type ResourceOut } from "@/lib/api/resources";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { joinNames } from "@/lib/mcp/serverState";

interface Props {
  servers: ResourceOut[];
  /** Clears the selection once the servers are off. */
  onDone: () => void;
}

export function McpSelectionPane({ servers, onDone }: Props) {
  const { t, i18n } = useTranslation();
  const bulk = useBulkMutate({
    invalidate: [resourcesKey, ...ownListKeysForKind("mcp_server")],
  });
  const on = servers.filter((s) => s.enabled);
  return (
    <EmptyState
      icon={Server}
      title={t("mcp.page.selectedTitle", { count: servers.length })}
      description={t("mcp.page.selectedBody", {
        names: joinNames(
          servers.map((s) => s.name),
          i18n.language,
        ),
      })}
      action={
        <Button
          variant="outline"
          disabled={bulk.isPending || on.length === 0}
          onClick={async () => {
            await bulk.run(on, (s) => resourcesApi.disable(s.uid));
            onDone();
          }}
        >
          <Power aria-hidden /> {t("mcp.page.turnOffMany", { count: servers.length })}
        </Button>
      }
    />
  );
}
