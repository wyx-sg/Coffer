// frontend/src/pages/ResourceDetailPage.tsx
//
// The /mcp-servers/:name detail route. The MCP servers surface only ever lists
// one kind, so the kind is fixed here rather than read off the URL — the old
// /mcp-servers/mcp_server/:name links are redirected by LegacyMcpServerRedirect.
import { McpServerDetailPage } from "./McpServerDetailPage";

export function ResourceDetailPage() {
  return <McpServerDetailPage />;
}
