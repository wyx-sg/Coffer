// frontend/src/components/mcp/add/addTestBody.ts — the Add server form as a
// `POST /resources/mcp_server/test-config` body (spec mcp-gateway "Test an
// unsaved server config before adding it").
//
// Plain rows go in `env` (stdio) or `headers` (HTTP). A Secret row with a
// typed value travels in `secret_values` for this test only — nothing is
// written to the keychain. A Secret row citing a stored secret goes in
// `secret_refs`, which the route answers `stored_secret_not_released`: a
// stored secret is released only to a server that is added and approved.
import type { McpConfigTestIn } from "@/lib/api/mcpTestConfig";
import type { NewServer } from "@/lib/mcp/importMcpServers";

export function addTestBodyOf(server: NewServer): McpConfigTestIn {
  const plain: Record<string, string> = {};
  const typed: Record<string, string> = {};
  const refs: Record<string, string> = {};
  for (const row of server.env) {
    if (!row.isSecret) plain[row.key] = row.value;
    else if (row.ref) refs[row.key] = row.ref;
    else typed[row.key] = row.value;
  }
  const transport: McpConfigTestIn["transport"] =
    server.transportType === "stdio"
      ? {
          type: "stdio",
          command: server.command,
          args: server.args,
          env: plain,
          secret_refs: refs,
          ...(server.cwd?.trim() ? { cwd: server.cwd.trim() } : {}),
        }
      : { type: "http", url: server.url, headers: plain, secret_refs: refs };
  return {
    name: server.name || null,
    transport,
    spawn_timeout_seconds: 30,
    request_timeout_seconds: 120,
    secret_values: typed,
  };
}

/** What the result was tested against, so an edit afterwards retires it. */
export function testKeyOf(body: McpConfigTestIn): string {
  return JSON.stringify({ ...body, name: null });
}
