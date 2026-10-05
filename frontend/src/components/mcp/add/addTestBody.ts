// frontend/src/components/mcp/add/addTestBody.ts — the Add server form as a
// `POST /resources/mcp_server/test-config` body (spec mcp-gateway "Test an
// unsaved server config before adding it").
//
// Plain rows go in `env` (stdio) or `headers` (HTTP). A new secret's value
// travels in `secret_values` for this test only — nothing is written to Secrets.
// A stored secret goes in `secret_refs`, which the route answers
// `stored_secret_not_released`: a stored secret is released only to a server
// that is added and approved.
import type { McpConfigTestIn } from "@/lib/api/mcpTestConfig";
import type { NewServer } from "@/lib/mcp/importMcpServers";
import { authSchemesField, keptRows, plainMapOfRows, secretRefsOfRows } from "@/lib/mcp/serverRows";

export function addTestBodyOf(server: NewServer): McpConfigTestIn {
  const plain = plainMapOfRows(server.env);
  const refs = secretRefsOfRows(keptRows(server.env).filter((r) => r.value.kind === "stored"));
  const typed: Record<string, string> = {};
  for (const r of keptRows(server.env)) {
    if (r.value.kind === "new") typed[r.key.trim()] = r.value.value;
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
      : {
          type: "http",
          url: server.url,
          headers: plain,
          secret_refs: refs,
          // Each typed secret is sent behind its row's scheme for this test.
          ...authSchemesField(server.env),
        };
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
