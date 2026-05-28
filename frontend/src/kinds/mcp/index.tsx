// frontend/src/kinds/mcp/index.tsx
import { Server } from "lucide-react";
import type { KindUIModule } from "@/lib/components/kindRegistry";
import { McpServerCard } from "./McpServerCard";
import { McpServerDetailPage } from "./McpServerDetailPage";

export const MCP_KIND_UI: KindUIModule = {
  name: "mcp_server",
  displayName: "MCP Server",
  icon: Server,
  Card: McpServerCard,
  // The name is read inside McpServerDetailPage via useParams; the prop
  // is accepted for type compatibility with the KindUIModule interface.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  DetailPage: ({ name: _name }) => <McpServerDetailPage />,
};
