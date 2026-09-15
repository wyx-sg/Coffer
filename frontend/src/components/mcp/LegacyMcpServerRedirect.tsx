// frontend/src/components/mcp/LegacyMcpServerRedirect.tsx
//
// Redirect a legacy `/mcp-servers/mcp_server/:name` deep link to
// `/mcp-servers/:name`. The kind segment only ever held one value — the MCP
// servers surface lists nothing but `mcp_server` — so it said nothing and was
// dropped from the route. Old bookmarks and links keep landing on the server.
// Lives in its own file so router.tsx stays component-free.
import { Navigate, useParams } from "react-router-dom";

export function LegacyMcpServerRedirect() {
  const name = useParams<{ name: string }>().name ?? "";
  return <Navigate to={`/mcp-servers/${name}`} replace />;
}
