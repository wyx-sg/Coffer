// frontend/src/kinds/mcp/index.tsx
import { Server } from "lucide-react";
import type { KindUIModule } from "@/lib/components/kindRegistry";
import { McpServerDetailPage } from "./McpServerDetailPage";

export const MCP_KIND_UI: KindUIModule = {
  name: "mcp_server",
  displayName: "MCP Server",
  icon: Server,
  // The MCP servers list now renders via McpServersTable (see ResourcesPage),
  // not a per-kind Card. This minimal Card satisfies the KindUIModule contract;
  // the only Card consumer (ResourceListView) is no longer wired into any page.
  Card: ({ resource }) => <span className="font-medium">{resource.name}</span>,
  // The name is read inside McpServerDetailPage via useParams; the prop
  // is accepted for type compatibility with the KindUIModule interface.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  DetailPage: ({ name: _name }) => <McpServerDetailPage />,
};
