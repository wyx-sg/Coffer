// e2e/mcp/specs/upstream_crash_recovery.spec.ts  (T-078)
//
// Use fake_mcp_server.py's "crash" scenario.  The upstream exits after the
// first tools/call.  The gateway's supervisor should detect the death and
// respawn the upstream so a second tools/call (after a brief wait) returns
// a SUCCESSFUL result — not merely "a reply arrived".

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

acceptance("001-mcp-gateway", "upstream crash recovery", async () => {
  const name = uniqueName("e2e-crash");
  // crash-after-calls=2: the upstream handles call #1 successfully, then
  // crashes on call #2.  After eviction+respawn the fresh upstream handles
  // the third call (#1 of its own lifetime) and returns a success.
  await registerMcpServer(name, [
    "--scenario",
    "crash",
    "--tools",
    "fragile_tool",
    "--crash-after-calls",
    "2",
  ]);

  const shim = spawnShim();
  try {
    sendEnvelope(shim, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {},
    });
    await readReply(shim);

    // First call — succeeds (crash_after_calls=2 so this one is fine)
    sendEnvelope(shim, {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: { name: `${name}__fragile_tool`, arguments: {} },
    });
    const first = await readReply(shim, 15_000);
    expect(first["id"]).toBe(2);
    // First call must succeed (it's call #1 out of the 2-call budget)
    expect((first as any).result).toBeDefined();

    // Second call — the upstream will crash (call #2 hits the limit)
    sendEnvelope(shim, {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: `${name}__fragile_tool`, arguments: {} },
    });
    // Crash call: accept error (upstream died) or success — just confirm reply arrives
    const crashCall = await readReply(shim, 15_000);
    expect(crashCall["id"]).toBe(3);

    // Third call — supervisor should have respawned the upstream.
    // No fixed sleep: the post-respawn readReply already uses a generous
    // 20 s timeout which covers the respawn + handshake latency.
    // The freshly-spawned server has call-count=0, so call #1 of its
    // lifetime succeeds before the crash limit is reached.
    // Assert this call returns a SUCCESSFUL result (result key present,
    // no error key) — the respawn completed successfully.
    sendEnvelope(shim, {
      jsonrpc: "2.0",
      id: 4,
      method: "tools/call",
      params: { name: `${name}__fragile_tool`, arguments: {} },
    });
    // Generous timeout to allow respawn + handshake
    const second = await readReply(shim, 20_000);
    expect(second["id"]).toBe(4);
    // Must be a successful result — not an error envelope.
    expect((second as any).result).toBeDefined();
    expect((second as any).error).toBeUndefined();
  } finally {
    await killShim(shim);
    await deregisterMcpServer(name);
  }
});
