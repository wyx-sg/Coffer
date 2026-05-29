// e2e/mcp/specs/mutating_upstream.spec.ts  (T-077)
//
// Use fake_mcp_server.py's "mutating" scenario to flip the tool list
// mid-session.  After one tools/call triggers the list_changed notification,
// assert:
//   1. The shim actually receives a notifications/tools/list_changed message.
//   2. After a re-list, the going_away tool is absent from the aggregate.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import {
  deregisterMcpServer,
  killShim,
  readMatchingReply,
  readReply,
  registerMcpServer,
  sendEnvelope,
  spawnShim,
  uniqueName,
} from "./_helpers";

acceptance(
  "001-mcp-gateway",
  "upstream tool list changes mid-session",
  async () => {
    const name = uniqueName("e2e-mut");
    // The fake server removes the FIRST tool after the mutation fires.
    // We order them so "going_away" is first and "stable_tool" is second,
    // meaning after the mutation "going_away" is removed and "stable_tool"
    // remains — making the assertions straightforward.
    await registerMcpServer(name, [
      "--scenario",
      "mutating",
      "--tools",
      "going_away",
      "stable_tool",
      "--notify-list-changed-after",
      "1",
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

      // Initial tool list
      sendEnvelope(shim, { jsonrpc: "2.0", id: 2, method: "tools/list" });
      const initialList = await readReply(shim);
      const initialTools = ((initialList as any).result?.tools ?? []).map(
        (t: any) => t.name as string,
      );
      expect(initialTools).toContain(`${name}__stable_tool`);
      expect(initialTools).toContain(`${name}__going_away`);

      // One call triggers the mutation inside the fake server, which will
      // send a notifications/tools/list_changed via the SSE channel.
      sendEnvelope(shim, {
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: { name: `${name}__stable_tool`, arguments: {} },
      });

      // Consume the tools/call reply (id:3) by waiting for a message with id 3.
      // The notification (no id) might arrive interleaved — use readMatchingReply
      // so we don't accidentally consume the notification here.
      await readMatchingReply(shim, (msg) => msg["id"] === 3, 15_000);

      // Assert the shim receives a notifications/tools/list_changed message.
      // This arrives via the SSE channel (no "id" field, has "method").
      // Give it up to 5s to propagate through the SSE pipeline.
      const notification = await readMatchingReply(
        shim,
        (msg) => msg["method"] === "notifications/tools/list_changed",
        5_000,
      );
      expect(notification["method"]).toBe("notifications/tools/list_changed");

      // Re-list — the going_away tool should have been removed
      sendEnvelope(shim, { jsonrpc: "2.0", id: 4, method: "tools/list" });
      const finalList = await readMatchingReply(
        shim,
        (msg) => msg["id"] === 4,
        10_000,
      );
      const finalTools = ((finalList as any).result?.tools ?? []).map(
        (t: any) => t.name as string,
      );

      // The mutating fixture removes the first tool after notify fires.
      // Assert the aggregate list is shorter than before.
      expect(finalTools.length).toBeLessThan(initialTools.length);
      // The removed tool must be absent.
      expect(finalTools).not.toContain(`${name}__going_away`);
    } finally {
      await killShim(shim);
      await deregisterMcpServer(name);
    }
  },
);
