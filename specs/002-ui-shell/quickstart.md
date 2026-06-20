# Quickstart — Coffer UI Shell

A 5-minute path from a fresh checkout to seeing the redesigned UI in your
browser, registering an MCP server through the GUI, and watching its first
invocation appear. This is the **GUI-focused** companion to
[`specs/001-mcp-gateway/quickstart.md`](../001-mcp-gateway/quickstart.md),
which covers the CLI + shim path.

## Prerequisites

- A working Coffer dev checkout. Backend deps installed
  (`uv sync` inside `backend/`), frontend deps installed
  (`pnpm install` or `npm install` inside `frontend/`).
- An MCP server you can register. The walk-through uses the public
  `@modelcontextprotocol/server-filesystem` (needs `npx`).
- An MCP client (Claude Code / Claude Desktop / Cursor) if you want to
  watch invocations land in the UI. The Add-MCP-server flow itself does
  not require a client.

## 1. Boot the dev stack

From the repo root:

```bash
make dev
```

`make dev` boots two processes:

- The daemon (`coffer daemon start`) on a free port in 8000–8009, writing
  `~/.coffer/daemon.json`.
- The Vite dev server on `http://localhost:5173/`. Vite's dev-only
  token-injection plugin (`frontend/vite.config.ts`) reads
  `~/.coffer/daemon.json` and injects the daemon token into the page so
  you don't have to paste anything by hand.

## 2. See the workbench

Open `http://localhost:5173/` in any modern browser.

The first time you visit, the index (`/`) redirects to `/agents` and you see:

- The redesigned sidebar — role-based groups: **Agents** (`/agents` — the
  agents you use), **Resources** (**MCP servers**, at `/mcp-servers`), and
  **System** (**Audit log** at `/audit`, **Settings**). The active route is
  highlighted. Click the collapse handle to switch between full and
  icon-only modes; your choice persists across reloads. (`/resources` still
  works — it's a legacy redirect to `/mcp-servers`.)
- The Agents welcome card explaining what Coffer is, with one primary action:
  **Add agent**. The matching **Add MCP server** welcome lives one click away
  on **MCP servers** (`/mcp-servers`).

If the daemon is not running (you skipped `make dev` or it crashed), you
see a "Daemon not running" view instead, with a Reload recovery control
(the desktop app offers Restart). Once the daemon is reachable again the
view recovers on the very next render — no manual reload needed (see the
`daemon-offline banner` acceptance scenario).

Switch the language between English and 中文 from the language switcher at
the bottom of the sidebar. The change takes effect on the next render and
persists in `localStorage` under `coffer.language`.

## 3. Add your first MCP server

Click **Add MCP server** on the welcome card (or the sidebar's MCP servers
list once you have one). A dialog opens.

Paste the standard `mcpServers` JSON block — the same block every MCP
server's README provides. For the filesystem example:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  }
}
```

You can paste one server or many at once. Click **Review**. The dialog
walks you through one screen per server so you can:

- Confirm the server name.
- Mark which `env` values are secrets. Secrets are encrypted into the
  credential store (`/api/v1/credentials`) rather than the resource config. The
  ordering is **register first, then write secrets to the store** so
  that a failed registration never leaves orphan credential entries (see
  the spec scenario).

Click **Add** to finish. On success the dialog closes and (for a single
server) the app navigates to `/mcp-servers/mcp_server/<name>` showing the
Overview tab. The new server appears in the resources list with health
"unknown", flipping to "healthy" within ~10 seconds.

If your JSON is malformed (parse error or wrong shape), the dialog stays
open and renders a readable error explaining what's wrong; nothing is sent
to the backend (see the `JSON import shows readable error for malformed
JSON` scenario).

## 4. Curate capabilities

On the server detail page, switch between the tabs:

- **Overview** — health, last seen, transport, namespace.
- **Tools / Resources / Prompts** — one row per capability with a
  per-capability enabled / disabled toggle. The search box narrows the
  list; toggling persists immediately and re-fetches the list.
- **Invocations** — a paged table showing per-call timestamp, type,
  capability, status, latency. Filter by status to drill down. Click any
  row to expand its raw log — the invocation's full underlying JSON record,
  pretty-printed in a monospace, scrollable block. Until any client calls a
  tool through Coffer, this tab shows a "No invocations yet" empty state
  with a hint about how to trigger one.

To watch an invocation land, point an MCP client at Coffer per
[`specs/001-mcp-gateway/quickstart.md`](../001-mcp-gateway/quickstart.md)
("Wire Coffer into your MCP client"), trigger a tool call (e.g. ask Claude
Code to read a file), then refresh the **Invocations** tab.

## 5. Audit log and settings

- `/audit` — the audit-log view (under the **System** group).
  Filter by time range and actor; click any row to expand its raw log —
  the entry's full underlying JSON record, pretty-printed in a monospace,
  scrollable block. The legacy `/observability` URL still resolves and
  redirects here. (Observability — system health / metrics — is a distinct
  surface reserved for the future, not this audit log.)
- `/settings` — tabs sidebar opening on **General** (default rows-per-page
  preference), plus **Data** (retention policy, manual prune, backups) and
  **About** (version / license / source).

You will notice three deliberately absent surfaces compared to the v0
shell:

- There is no "Daemon" tab and no daemon-status panel. The daemon is an
  implementation detail; if it goes down, the daemon-offline banner is
  the one signal you see.
- There is no "Shutdown daemon" button — it would kill the very page
  you're on; use `coffer daemon stop` from the CLI.
- There is no "Rotate token" button — use `coffer daemon rotate-token`.

## Where things live

- Daemon state: `~/.coffer/coffer.db` and `~/.coffer/daemon.json`
  (unchanged from spec 001).
- UI preferences: `localStorage` only — `coffer.language` (selected
  language) and `coffer.nav.collapsed` (sidebar mode).
- UI source: `frontend/src/` — see [`plan.md`](./plan.md) for the layout.
