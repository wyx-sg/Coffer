// e2e/mcp/specs/_helpers.ts
//
// Shared utilities for the cross-process MCP e2e suite.
// The webServer fixture in playwright.config.ts ensures a coffer daemon is
// already running on port 18000 with an isolated HOME written to
// /tmp/coffer-e2e-home.path before any test runs.

import * as child_process from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const REPO_ROOT = path.resolve(__dirname, "../../..");
const PYTHON = path.join(REPO_ROOT, ".venv/bin/python3");
const FAKE_SERVER = path.join(
  REPO_ROOT,
  "backend/tests/fixtures/fake_mcp_server.py",
);

// ---------------------------------------------------------------------------
// Daemon discovery
// ---------------------------------------------------------------------------

export interface DaemonInfo {
  port: number;
  token: string;
}

/**
 * Read the daemon's token and port from the sentinel file written by
 * start_daemon.sh.  The daemon writes ~/.coffer/daemon.json; in the e2e
 * suite HOME is overridden by the script and the chosen path is persisted
 * to /tmp/coffer-e2e-home.path so we can find it from any spec file.
 */
export function readDaemonToken(): DaemonInfo {
  const homePath = fs.readFileSync("/tmp/coffer-e2e-home.path", "utf-8").trim();
  const json = fs.readFileSync(`${homePath}/.coffer/daemon.json`, "utf-8");
  const parsed = JSON.parse(json) as { token: string; port: number };
  return { token: parsed.token, port: parsed.port };
}

// ---------------------------------------------------------------------------
// Resource registration helpers
// ---------------------------------------------------------------------------

/**
 * Register an mcp_server resource backed by fake_mcp_server.py.
 * `extraArgs` are appended verbatim to the Python command line.
 */
export async function registerMcpServer(
  name: string,
  extraArgs: string[] = ["--tools", "read_file"],
): Promise<void> {
  const { port, token } = readDaemonToken();
  const response = await fetch(`http://127.0.0.1:${port}/api/v1/resources`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e-mcp",
    },
    body: JSON.stringify({
      kind: "mcp_server",
      name,
      config: {
        transport: {
          type: "stdio",
          command: PYTHON,
          args: [FAKE_SERVER, ...extraArgs],
        },
      },
    }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `registerMcpServer(${name}) failed: ${response.status} ${body}`,
    );
  }
}

/**
 * Deregister an mcp_server resource. Best-effort; errors are logged but not
 * rethrown so the test cleanup path doesn't mask real failures.
 */
export async function deregisterMcpServer(name: string): Promise<void> {
  const { port, token } = readDaemonToken();
  try {
    await fetch(
      `http://127.0.0.1:${port}/api/v1/resources/mcp_server/${name}`,
      {
        method: "DELETE",
        headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-mcp" },
      },
    );
  } catch {
    // best-effort cleanup
  }
}

// ---------------------------------------------------------------------------
// Shim subprocess helpers
// ---------------------------------------------------------------------------

export interface ShimHandle {
  proc: child_process.ChildProcessWithoutNullStreams;
  /** Lines received from stdout that haven't been consumed yet. */
  pendingLines: string[];
  closed: boolean;
}

/**
 * Spawn a coffer-mcp-shim subprocess pointing at the running daemon.
 * stdout lines are buffered in `handle.pendingLines`.
 */
export function spawnShim(): ShimHandle {
  const homePath = fs.readFileSync("/tmp/coffer-e2e-home.path", "utf-8").trim();
  const proc = child_process.spawn(
    PYTHON,
    ["-m", "coffer.surfaces.shim.main"],
    {
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        HOME: homePath,
        PYTHONPATH: path.join(REPO_ROOT, "backend"),
      },
    },
  );

  const handle: ShimHandle = { proc, pendingLines: [], closed: false };

  let buffer = "";
  proc.stdout.on("data", (chunk: Buffer) => {
    buffer += chunk.toString("utf-8");
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl);
      buffer = buffer.slice(nl + 1);
      if (line.trim()) {
        handle.pendingLines.push(line);
      }
    }
  });

  proc.on("close", () => {
    handle.closed = true;
  });

  return handle;
}

/**
 * Write a JSON-RPC envelope to the shim's stdin as a newline-delimited line.
 */
export function sendEnvelope(shim: ShimHandle, envelope: unknown): void {
  shim.proc.stdin.write(JSON.stringify(envelope) + "\n");
}

/**
 * Read the next complete JSON-RPC reply from the shim's stdout.
 * Polls `pendingLines` up to `timeoutMs` milliseconds before throwing.
 */
export async function readReply(
  shim: ShimHandle,
  timeoutMs = 10_000,
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (shim.pendingLines.length > 0) {
      const line = shim.pendingLines.shift()!;
      return JSON.parse(line) as Record<string, unknown>;
    }
    if (shim.closed) {
      throw new Error("shim process closed before a reply arrived");
    }
    await new Promise<void>((r) => setTimeout(r, 50));
  }
  throw new Error(
    `readReply timed out after ${timeoutMs}ms (pending: ${shim.pendingLines.length})`,
  );
}

/**
 * Gracefully stop a shim: close stdin, wait up to 3 s, then SIGKILL.
 */
export async function killShim(shim: ShimHandle): Promise<void> {
  if (shim.closed) return;
  shim.proc.stdin.end();
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      shim.proc.kill("SIGKILL");
      resolve();
    }, 3_000);
    shim.proc.on("close", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

/**
 * Read JSON-RPC messages from the shim until one satisfies `predicate` or
 * the timeout fires.  Non-matching messages are pushed to the FRONT of
 * `pendingLines` so that a subsequent readReply/readMatchingReply can see
 * them — callers can safely look for a specific message without discarding
 * interleaved messages.
 */
export async function readMatchingReply(
  shim: ShimHandle,
  predicate: (msg: Record<string, unknown>) => boolean,
  timeoutMs = 10_000,
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + timeoutMs;
  const skipped: string[] = [];
  try {
    while (Date.now() < deadline) {
      if (shim.pendingLines.length > 0) {
        const line = shim.pendingLines.shift()!;
        const msg = JSON.parse(line) as Record<string, unknown>;
        if (predicate(msg)) return msg;
        // Non-matching message — save for later.
        skipped.push(line);
        continue;
      }
      if (shim.closed) {
        throw new Error("shim process closed before a matching reply arrived");
      }
      await new Promise<void>((r) => setTimeout(r, 50));
    }
  } finally {
    // Restore skipped messages to the FRONT of pendingLines so they remain
    // available to future reads.
    shim.pendingLines.unshift(...skipped);
  }
  throw new Error(
    `readMatchingReply timed out after ${timeoutMs}ms (pending: ${shim.pendingLines.length})`,
  );
}

/**
 * Generate a collision-resistant name for a test resource.
 */
export function uniqueName(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * Poll `GET /resources/mcp_server/{name}/capabilities` until all
 * `expectedPrefixedNames` appear in the returned tools list, or the timeout
 * fires.  Throws if the precondition is not met in time.
 *
 * Use this after POST /refresh to wait for capability discovery to settle
 * before proceeding with enable/disable operations.  Without the poll, a race
 * exists between the /refresh HTTP response returning and the preference rows
 * being visible to subsequent reads in concurrent test runs.
 */
export async function waitForCapabilities(
  serverName: string,
  expectedPrefixedNames: string[],
  timeoutMs = 10_000,
): Promise<void> {
  const { port, token } = readDaemonToken();
  const url = `http://127.0.0.1:${port}/api/v1/resources/mcp_server/${serverName}/capabilities`;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    let present: string[] = [];
    try {
      const res = await fetch(url, {
        headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-wait" },
      });
      if (res.ok) {
        const body = (await res.json()) as {
          tools?: Array<{ prefixed_name: string }>;
        };
        present = (body.tools ?? []).map((t) => t.prefixed_name);
      }
    } catch {
      // transient fetch error — just retry
    }

    const allPresent = expectedPrefixedNames.every((n) => present.includes(n));
    if (allPresent) return;

    await new Promise<void>((r) => setTimeout(r, 200));
  }

  throw new Error(
    `waitForCapabilities(${serverName}) timed out after ${timeoutMs}ms — ` +
      `expected ${JSON.stringify(expectedPrefixedNames)} to appear in /capabilities`,
  );
}
