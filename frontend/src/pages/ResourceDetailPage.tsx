// frontend/src/pages/ResourceDetailPage.tsx
//
// The /mcp-servers/:uid detail route. The MCP servers surface only ever lists
// one kind, so the kind is fixed in the page below rather than read off the URL
// — and with a uid in the path there is nothing for a kind segment to
// disambiguate anyway.
import { McpServerDetailPage } from "./McpServerDetailPage";

export function ResourceDetailPage() {
  return <McpServerDetailPage />;
}
