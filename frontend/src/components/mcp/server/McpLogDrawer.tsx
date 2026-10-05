// src/components/mcp/server/McpLogDrawer.tsx — "<name> · Server log", a 640 drawer over the MCP servers page (design 4.1.16).
//
// stdio servers only: what the server printed on stderr and how Coffer started
// and stopped it. No tabs — a server's calls are on the Activity page.
import type { ResourceOut } from "@/lib/api/resources";
import { useTranslation } from "react-i18next";

import { McpDrawer } from "./McpDrawer";
import { McpServerLogView } from "./McpServerLogView";

interface Props {
  resource: ResourceOut;
  open: boolean;
  onClose: () => void;
}

export function McpLogDrawer({ resource, open, onClose }: Props) {
  const { t } = useTranslation();
  return (
    <McpDrawer
      open={open}
      onClose={onClose}
      testId="mcp-log-drawer"
      title={t("mcp.page.log.title", { name: resource.name })}
      subtitle={t("mcp.page.log.subtitleStdio")}
    >
      <McpServerLogView serverUid={resource.uid} />
    </McpDrawer>
  );
}
