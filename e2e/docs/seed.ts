// e2e/docs/seed.ts
//
// The demo workspace every docs image shows: two agents, a few MCP servers (some
// working, two that need the person), skills, a secret and a knowledge
// collection. It is made through the daemon's own REST API, so a route that
// changes breaks this loudly. Names are the docs' one cast: a guide and the home
// page tell the same story.
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

import { DOCS_HOME } from "./env";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const PYTHON = path.join(REPO_ROOT, ".venv/bin/python3");
const DEMO_SERVER = path.join(REPO_ROOT, "e2e/docs/demo_mcp_server.py");

interface Daemon {
  base: string;
  headers: Record<string, string>;
}

function daemon(): Daemon {
  const json = fs.readFileSync(
    path.join(DOCS_HOME, ".coffer", "daemon.json"),
    "utf-8",
  );
  const { token, port } = JSON.parse(json) as { token: string; port: number };
  return {
    base: `http://127.0.0.1:${port}/api/v1`,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "docs-shots",
    },
  };
}

async function post(route: string, body: unknown, ok: number[] = [200, 201]) {
  const { base, headers } = daemon();
  const res = await fetch(`${base}${route}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!ok.includes(res.status)) {
    throw new Error(`POST ${route} -> ${res.status} ${await res.text()}`);
  }
  return res;
}

/** Stand-in `claude` and `codex` programs, so both agents read as installed. */
function installAgentPrograms(): void {
  const bin = path.join(DOCS_HOME, "bin");
  fs.mkdirSync(bin, { recursive: true });
  const programs: Record<string, string> = {
    claude: "2.1.281 (Claude Code)",
    codex: "codex-cli 0.41.0",
  };
  for (const [name, version] of Object.entries(programs)) {
    fs.writeFileSync(path.join(bin, name), `#!/bin/sh\necho "${version}"\n`, {
      mode: 0o755,
    });
  }
  // Conversations lists Codex's sessions by asking `codex app-server`, so the
  // stand-in answers that one conversation with a few demo threads.
  fs.writeFileSync(path.join(bin, "codex"), CODEX_STAND_IN, { mode: 0o755 });
}

const CODEX_STAND_IN = `#!/usr/bin/env python3
import json, sys, time
if sys.argv[1:2] != ["app-server"]:
    print("codex-cli 0.41.0")
    sys.exit(0)
NOW = int(time.time())
THREADS = [
    ("t1", "Fix the flaky login test", "/Users/demo/work/web-app", 3600),
    ("t2", "Draft release notes for 2.4", "/Users/demo/work/api", 86400),
    ("t3", "Explain the retry logic in the queue worker", "/Users/demo/work/api", 172800),
]
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    if msg.get("method") == "thread/list":
        result = {"data": [
            {"id": i, "name": n, "cwd": c, "createdAt": NOW - a - 600, "updatedAt": NOW - a}
            for i, n, c, a in THREADS
        ], "nextCursor": None}
    else:
        result = {}
    print(json.dumps({"id": msg["id"], "result": result}), flush=True)
`;

// name -> tool:description. Each runs as a program named `<name>-mcp` in the
// demo HOME's `bin`, so a server's command reads like a real one and no path
// from the machine that took the picture shows up in it.
const WORKING_SERVERS: Array<[string, string[]]> = [
  [
    "github",
    [
      "create_issue:Open an issue in a repository.",
      "list_pull_requests:List the pull requests of a repository.",
      "get_file_contents:Read a file from a repository.",
    ],
  ],
  [
    "filesystem",
    [
      "read_file:Read the contents of a file.",
      "write_file:Create or overwrite a file.",
      "list_directory:List the entries of a directory.",
    ],
  ],
  [
    "linear",
    [
      "search_issues:Search issues by text, team or assignee.",
      "create_issue:Create an issue in a team.",
    ],
  ],
];

const NEEDS_YOU_SERVERS = ["sentry", "postgres"];

const SKILLS: Array<[string, string]> = [
  ["pdf", "Read, fill and create PDF files."],
  ["gh-triage", "Sort new GitHub issues by area and urgency."],
  ["release-notes", "Draft release notes from merged pull requests."],
];

const NOTES: Array<[string, string]> = [
  [
    "deploy-checklist.md",
    "# Deploy checklist\n\nRun the migrations, then restart the workers.\n",
  ],
  [
    "oncall-handbook.md",
    "# On-call handbook\n\nWho to page, and what to check first.\n",
  ],
  [
    "api-conventions.md",
    "# API conventions\n\nResources are plural. Errors carry a stable code.\n",
  ],
];

export async function seedDemoWorkspace(): Promise<void> {
  // Playwright runs this again in a fresh worker after a failed scenario; the
  // daemon is the same one, already seeded.
  const { base, headers } = daemon();
  const seeded = await fetch(`${base}/agents`, { headers });
  if (((await seeded.json()) as { items: unknown[] }).items.length > 0) return;

  installAgentPrograms();

  for (const type of ["claude_code", "codex"]) {
    const configDir = path.join(DOCS_HOME, `${type}-config`);
    fs.mkdirSync(configDir, { recursive: true });
    const agent = await post("/agents", { type, config_dir: configDir });
    // Claude Code is connected; Codex is left for the Overview to point at.
    if (type === "claude_code") {
      const { uid } = (await agent.json()) as { uid: string };
      await post(`/agents/${uid}/coffer-connection`, {});
    }
  }

  for (const [name, tools] of WORKING_SERVERS) {
    const launcher = path.join(DOCS_HOME, "bin", `${name}-mcp`);
    const quoted = [name, ...tools].map((a) => `'${a.replace(/'/g, "'\\''")}'`);
    fs.writeFileSync(
      launcher,
      `#!/bin/sh\nexec "${PYTHON}" "${DEMO_SERVER}" ${quoted.join(" ")}\n`,
      { mode: 0o755 },
    );
    await post("/resources", {
      kind: "mcp_server",
      name,
      config: {
        transport: {
          type: "stdio",
          command: `${name}-mcp`,
          args: [],
        },
      },
    });
  }
  for (const name of NEEDS_YOU_SERVERS) {
    await post("/resources", {
      kind: "mcp_server",
      name,
      config: {
        // A launcher that is not on this machine: the server fails, and the
        // Overview says so. The names are not programs anyone installs.
        transport: { type: "stdio", command: `${name}-mcp`, args: [] },
      },
    });
  }

  for (const [name, description] of SKILLS) {
    const dir = path.join(DOCS_HOME, "skill-sources", name);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "SKILL.md"),
      `---\nname: ${name}\ndescription: ${description}\n---\n\n# ${name}\n\n${description}\n`,
    );
    await post("/skills/import", { path: dir });
  }

  await post("/secrets", { label: "LINEAR_API_KEY", value: "demo-not-a-key" });

  // A custom-tool group, so that page shows a lived-in workspace.
  await post("/custom-tools", {
    name: "orders-api",
    base_url: "https://orders.example.com/v1",
    tools: [
      {
        name: "get_order",
        description: "Read one order by id.",
        method: "GET",
        path: "/orders/{id}",
        input_schema: {
          type: "object",
          properties: { id: { type: "string" } },
          required: ["id"],
        },
      },
      {
        name: "list_orders",
        description: "List recent orders.",
        method: "GET",
        path: "/orders",
        input_schema: { type: "object", properties: {} },
      },
    ],
  });

  const created = await post("/knowledge/collections", {
    name: "engineering",
    description: "How we build and run our services.",
  });
  const { name: collection } = (await created.json()) as { name: string };
  const { "Content-Type": _json, ...multipartHeaders } = headers;
  for (const [file, body] of NOTES) {
    const form = new FormData();
    form.set("collection", collection);
    form.set("file", new Blob([body], { type: "text/markdown" }), file);
    const res = await fetch(`${base}/knowledge/upload`, {
      method: "POST",
      headers: multipartHeaders,
      body: form,
    });
    if (!res.ok) throw new Error(`upload ${file} -> ${res.status}`);
  }
}
