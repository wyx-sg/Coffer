// frontend/src/lib/hooks/useMcpCapabilityPreview.ts — read a resource, fill a prompt, for a row's details (spec mcp-gateway "Preview a resource or a prompt from the server page").
//
// Asked for on demand, one row at a time, and never cached: what the server
// answers now is the point. No toast on error: the row's details render the
// failure inline under the button that asked.
import { useMutation } from "@tanstack/react-query";

import { mcpServersApi } from "@/lib/api/mcpServers";

export function useReadMcpResource(serverUid: string) {
  return useMutation({
    mutationFn: (uri: string) => mcpServersApi.readResource(serverUid, uri),
  });
}

export function useGetMcpPrompt(serverUid: string) {
  return useMutation({
    mutationFn: (vars: { name: string; args: Record<string, string> }) =>
      mcpServersApi.getPrompt(serverUid, vars.name, vars.args),
  });
}
