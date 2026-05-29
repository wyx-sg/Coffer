// e2e/mcp/specs/concurrent_clients.spec.ts  (T-076)
//
// Spawn two shim subprocesses simultaneously against the same daemon.
// Assert that each sees ALL aggregated tools (gateway merges all servers)
// and that concurrent tool calls complete independently with no cross-talk
// (SC-004).

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
  waitForCapabilities,
} from "./_helpers";

acceptance("001-mcp-gateway", "concurrent clients", async () => {
  const nameA = uniqueName("e2e-conc-a");
  const nameB = uniqueName("e2e-conc-b");
  await registerMcpServer(nameA, ["--tools", "alpha_tool"]);
  await registerMcpServer(nameB, ["--tools", "beta_tool"]);

  // Wait for the process supervisor to confirm both servers are reachable
  // before spawning the shim clients.  Without this, the MCP session's own
  // per-session supervisor may encounter a transient spawn failure on the
  // second consecutive run (reused daemon, higher process-spawn load) and
  // return an empty tool list.  Mirroring the pattern in capability_disable.
  await waitForCapabilities(nameA, [`${nameA}__alpha_tool`]);
  await waitForCapabilities(nameB, [`${nameB}__beta_tool`]);

  const shimA = spawnShim();
  const shimB = spawnShim();
  try {
    // Initialize both shims
    sendEnvelope(shimA, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {},
    });
    sendEnvelope(shimB, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {},
    });
    const [initA, initB] = await Promise.all([
      readReply(shimA),
      readReply(shimB),
    ]);
    expect((initA as any).result?.serverInfo?.name).toBe("coffer");
    expect((initB as any).result?.serverInfo?.name).toBe("coffer");

    // List tools on both — gateway aggregates all registered servers
    sendEnvelope(shimA, { jsonrpc: "2.0", id: 2, method: "tools/list" });
    sendEnvelope(shimB, { jsonrpc: "2.0", id: 2, method: "tools/list" });
    const [listA, listB] = await Promise.all([
      readReply(shimA),
      readReply(shimB),
    ]);

    const toolsA = ((listA as any).result?.tools ?? []).map(
      (t: any) => t.name as string,
    );
    const toolsB = ((listB as any).result?.tools ?? []).map(
      (t: any) => t.name as string,
    );

    // Each shim sees both servers' tools
    expect(toolsA).toContain(`${nameA}__alpha_tool`);
    expect(toolsA).toContain(`${nameB}__beta_tool`);
    expect(toolsB).toContain(`${nameA}__alpha_tool`);
    expect(toolsB).toContain(`${nameB}__beta_tool`);

    // Interleaved tool calls — assert correct IDs come back (no cross-talk)
    sendEnvelope(shimA, {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: `${nameA}__alpha_tool`, arguments: {} },
    });
    sendEnvelope(shimB, {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: `${nameB}__beta_tool`, arguments: {} },
    });
    const [callA, callB] = await Promise.all([
      readReply(shimA, 15_000),
      readReply(shimB, 15_000),
    ]);

    expect(callA["id"]).toBe(3);
    expect(callB["id"]).toBe(3);
    expect((callA as any).result).toBeDefined();
    expect((callB as any).result).toBeDefined();
  } finally {
    await Promise.all([killShim(shimA), killShim(shimB)]);
    await Promise.all([deregisterMcpServer(nameA), deregisterMcpServer(nameB)]);
  }
});
