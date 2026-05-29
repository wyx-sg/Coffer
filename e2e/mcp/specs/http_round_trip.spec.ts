// e2e/mcp/specs/http_round_trip.spec.ts
//
// Start a real HTTP MCP upstream (fake_mcp_server.py --transport http),
// register it with transport.type="http", drive the shim, and assert
// tool list + call succeed through the gateway.

import * as child_process from "node:child_process";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import {
  deregisterMcpServer,
  killShim,
  readDaemonToken,
  readMatchingReply,
  readReply,
  sendEnvelope,
  spawnShim,
  uniqueName,
} from "./_helpers";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../..");
const PYTHON = path.join(REPO_ROOT, ".venv/bin/python3");
const FAKE_SERVER = path.join(
  REPO_ROOT,
  "backend/tests/fixtures/fake_mcp_server.py",
);

/** Start fake_mcp_server in HTTP mode and wait for the READY line. */
async function startHttpFakeServer(tools: string[]): Promise<{
  proc: child_process.ChildProcessWithoutNullStreams;
  port: number;
}> {
  const proc = child_process.spawn(
    PYTHON,
    [FAKE_SERVER, "--transport", "http", "--port", "0", "--tools", ...tools],
    { stdio: ["pipe", "pipe", "pipe"] },
  );

  const port = await new Promise<number>((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error("HTTP fake server timed out")),
      15_000,
    );
    let buf = "";
    proc.stdout.on("data", (chunk: Buffer) => {
      buf += chunk.toString("utf-8");
      const m = /READY port=(\d+)/.exec(buf);
      if (m) {
        clearTimeout(timeout);
        resolve(parseInt(m[1], 10));
      }
    });
    proc.on("close", (code) => {
      clearTimeout(timeout);
      reject(new Error(`HTTP fake server exited with code ${code}`));
    });
  });

  return { proc, port };
}

/** Register an MCP server with HTTP transport via the REST API. */
async function registerHttpMcpServer(
  name: string,
  port: number,
): Promise<void> {
  const { port: daemonPort, token } = readDaemonToken();
  const response = await fetch(
    `http://127.0.0.1:${daemonPort}/api/v1/resources`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Coffer-Token": token,
        "X-Coffer-Actor": "e2e-http",
      },
      body: JSON.stringify({
        kind: "mcp_server",
        name,
        config: {
          transport: {
            type: "http",
            url: `http://127.0.0.1:${port}/mcp`,
          },
        },
      }),
    },
  );
  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `registerHttpMcpServer(${name}) failed: ${response.status} ${body}`,
    );
  }
}

acceptance(
  "001-mcp-gateway",
  "HTTP-transport MCP server round trip",
  async () => {
    const name = uniqueName("e2e-http");
    let fakeProc: child_process.ChildProcessWithoutNullStreams | null = null;

    try {
      // 1. Start the HTTP upstream
      const { proc, port } = await startHttpFakeServer([
        "http_read",
        "http_write",
      ]);
      fakeProc = proc;

      // 2. Register the resource with HTTP transport
      await registerHttpMcpServer(name, port);

      // 3. Spawn the shim and drive JSON-RPC through it
      const shim = spawnShim();
      try {
        // initialize
        sendEnvelope(shim, {
          jsonrpc: "2.0",
          id: 1,
          method: "initialize",
          params: {},
        });
        const init = await readReply(shim);
        expect(init["id"]).toBe(1);
        expect((init as any).result?.serverInfo?.name).toBe("coffer");

        // tools/list — must include the namespaced HTTP tools.
        // Use readMatchingReply so an interleaved notification doesn't consume
        // the wrong line.
        sendEnvelope(shim, { jsonrpc: "2.0", id: 2, method: "tools/list" });
        const list = await readMatchingReply(
          shim,
          (m) => m["id"] === 2,
          15_000,
        );
        const tools = ((list as any).result?.tools ?? []) as Array<{
          name: string;
        }>;
        expect(tools.some((t) => t.name === `${name}__http_read`)).toBe(true);

        // tools/call — drive a real tool call through the HTTP upstream.
        // Use readMatchingReply for the same reason.
        sendEnvelope(shim, {
          jsonrpc: "2.0",
          id: 3,
          method: "tools/call",
          params: { name: `${name}__http_read`, arguments: {} },
        });
        const call = await readMatchingReply(
          shim,
          (m) => m["id"] === 3,
          15_000,
        );
        expect(call["id"]).toBe(3);
        // Result must be a success (no top-level error key)
        expect((call as any).result).toBeDefined();
        expect((call as any).error).toBeUndefined();
      } finally {
        await killShim(shim);
      }
    } finally {
      await deregisterMcpServer(name);
      if (fakeProc && !fakeProc.killed) {
        fakeProc.kill("SIGTERM");
      }
    }
  },
);
