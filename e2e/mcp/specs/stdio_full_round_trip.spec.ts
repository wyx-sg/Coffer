// e2e/mcp/specs/stdio_full_round_trip.spec.ts  (T-075)
//
// Spawn a real coffer-mcp-shim, drive JSON-RPC over its stdin, and assert
// replies come back on stdout.  This covers the "register a stdio MCP server"
// acceptance scenario end-to-end at the OS-process level — the same path
// Claude Desktop / Cursor take.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import {
  deregisterMcpServer,
  killShim,
  readReply,
  registerMcpServer,
  sendEnvelope,
  spawnShim,
  uniqueName,
} from "./_helpers";

acceptance("001-mcp-gateway", "register a stdio MCP server", async () => {
  const name = uniqueName("e2e-stdio");
  await registerMcpServer(name, ["--tools", "read_file"]);

  const shim = spawnShim();
  try {
    // 1. initialize
    sendEnvelope(shim, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {},
    });
    const init = await readReply(shim);
    expect(init["id"]).toBe(1);
    const initResult = (init as any).result;
    expect(initResult?.serverInfo?.name).toBe("coffer");

    // 2. tools/list
    sendEnvelope(shim, { jsonrpc: "2.0", id: 2, method: "tools/list" });
    const list = await readReply(shim);
    const tools = (list as any).result?.tools as Array<{ name: string }>;
    expect(tools).toBeDefined();
    expect(tools.some((t) => t.name === `${name}__read_file`)).toBe(true);

    // 3. tools/call
    sendEnvelope(shim, {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: `${name}__read_file`, arguments: {} },
    });
    const call = await readReply(shim, 15_000);
    expect(call["id"]).toBe(3);
    expect((call as any).result).toBeDefined();
  } finally {
    await killShim(shim);
    await deregisterMcpServer(name);
  }
});
