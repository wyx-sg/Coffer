// e2e/mcp/specs/capability_disable.spec.ts
//
// Register a stdio server; disable one of its tools via the REST API;
// then through the shim assert that:
//   (a) tools/list omits the disabled tool, and
//   (b) tools/call on the disabled tool returns a JSON-RPC error
//       (not a successful result).

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import {
  deregisterMcpServer,
  killShim,
  readDaemonToken,
  readReply,
  registerMcpServer,
  sendEnvelope,
  spawnShim,
  uniqueName,
  waitForCapabilities,
} from "./_helpers";

/**
 * Trigger capability discovery for a server via the /refresh endpoint.
 * This ensures capability preference rows exist in the DB so that
 * enable/disable calls can find them.
 */
async function refreshCapabilities(serverName: string): Promise<void> {
  const { port, token } = readDaemonToken();
  const url = `http://127.0.0.1:${port}/api/v1/resources/mcp_server/${serverName}/refresh`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e-cap-disable",
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `refreshCapabilities(${serverName}) failed: ${response.status} ${body}`,
    );
  }
}

/** Disable a specific tool via the REST API. */
async function disableTool(
  serverName: string,
  toolName: string,
): Promise<void> {
  const { port, token } = readDaemonToken();
  const url =
    `http://127.0.0.1:${port}/api/v1/resources/mcp_server/${serverName}` +
    `/capabilities/tool/${toolName}/disable`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e-cap-disable",
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `disableTool(${serverName}, ${toolName}) failed: ${response.status} ${body}`,
    );
  }
}

acceptance(
  "001-mcp-gateway",
  "disabled capability rejected through the shim",
  async () => {
    const name = uniqueName("e2e-dis");
    // Expose two tools so we can verify the disabled one is absent while the
    // enabled one is still present.
    await registerMcpServer(name, ["--tools", "keep_tool", "remove_tool"]);

    // Trigger capability discovery so the preference rows exist in the DB.
    // The disable endpoint requires the row to be present (set_enabled returns
    // null → 404 if the row doesn't exist yet).
    await refreshCapabilities(name);

    // Poll until both tools appear in the capabilities list. This guards
    // against the race where /refresh returns 200 but the preference rows
    // haven't propagated to the query layer yet (observed under load in
    // back-to-back e2e runs). Without this wait, disableTool() can return
    // 404 if the row doesn't exist yet.
    await waitForCapabilities(name, [
      `${name}__keep_tool`,
      `${name}__remove_tool`,
    ]);

    // Disable one tool via the REST API.
    await disableTool(name, "remove_tool");

    const shim = spawnShim();
    try {
      // Initialize
      sendEnvelope(shim, {
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {},
      });
      const init = await readReply(shim);
      expect(init["id"]).toBe(1);

      // tools/list — disabled tool must be absent; enabled tool must be present
      sendEnvelope(shim, { jsonrpc: "2.0", id: 2, method: "tools/list" });
      const listReply = await readReply(shim, 15_000);
      const tools = ((listReply as any).result?.tools ?? []).map(
        (t: any) => t.name as string,
      );
      expect(tools).toContain(`${name}__keep_tool`);
      expect(tools).not.toContain(`${name}__remove_tool`);

      // tools/call on the disabled tool — the gateway returns a JSON-RPC error
      // (code -32000, per protocol_routes.py _JSON_RPC_COFFER_TOOL_DISABLED).
      sendEnvelope(shim, {
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: { name: `${name}__remove_tool`, arguments: {} },
      });
      const callReply = await readReply(shim, 10_000);
      expect(callReply["id"]).toBe(3);
      // Must be an error envelope — no "result" key, has "error" key.
      expect((callReply as any).error).toBeDefined();
      expect((callReply as any).result).toBeUndefined();
      // The error code is -32000 (TOOL_DISABLED).
      expect((callReply as any).error?.code).toBe(-32000);
    } finally {
      await killShim(shim);
      await deregisterMcpServer(name);
    }
  },
);
