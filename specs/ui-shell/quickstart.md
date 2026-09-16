# Quickstart — Coffer UI Shell

A 5-minute path from a fresh checkout to seeing the redesigned UI in your
browser, registering an MCP server through the GUI, and watching its first
invocation appear. This is the **GUI-focused** companion to
[`specs/mcp-gateway/quickstart.md`](../mcp-gateway/quickstart.md),
which covers the CLI + shim path.

## Prerequisites

- A working Coffer dev checkout. Backend deps installed
  (`uv sync` inside `backend/`), frontend deps installed
  (`pnpm install` or `npm install` inside `frontend/`).
- An MCP server you can register. The walk-through uses the public
  `@modelcontextprotocol/server-filesystem` (needs `npx`).
- An MCP client (Claude Code / Claude Desktop / any stdio MCP client) if you want to
  watch invocations land in the UI. The Add-MCP-server flow itself does
  not require a client.

## 1. Boot the dev stack

From the repo root:

```bash
make dev
```

`make dev` boots two processes:

- The daemon (`coffer daemon start`) on port 8000 — fixed, not scanned; it
  refuses to start rather than moving if something else holds it (FR-028) —
  writing `~/.coffer/daemon.json`.
- The Vite dev server on `http://localhost:5173/`. Vite's dev-only
  token-injection plugin (`frontend/vite.config.ts`) reads
  `~/.coffer/daemon.json` and injects the daemon token into the page so
  you don't have to paste anything by hand.

## 2. See the workbench

Open `http://localhost:5173/` in any modern browser.

The first time you visit, the index (`/`) redirects to `/agents` and you see:

- The redesigned sidebar — role-based groups: **Agents** (**Agents** at
  `/agents`, **Chat** at `/chat`), **Resources** (**MCP servers**, **Skills**,
  **Knowledge**, **Memory**, **Model providers**, **Channels**), and **System**
  (**Activity** at `/activity`, **Sync**, **Settings**). The active route is
  highlighted. Click the collapse handle to switch between full and icon-only
  modes; your choice persists across reloads. (`/resources` still works — it's
  a legacy redirect to `/mcp-servers`.)
- The Agents welcome card explaining what Coffer is, with one primary action:
  **Add agent**. The matching **Add MCP server** welcome lives one click away
  on **MCP servers** (`/mcp-servers`).

If the daemon is not running (you skipped `make dev` or it crashed), you see a
"Daemon not running" view instead. In a browser it shows the command to run —
`coffer daemon start` — and no button: the page cannot start a daemon, and the
status query polls every 30s, so the banner clears itself once the daemon is
back (see the `daemon-offline banner` acceptance scenario). The desktop shell is
the exception: it can spawn one, so there the banner carries a Restart control.

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
server) the app navigates to `/mcp-servers/<name>` showing the Overview tab
(`/mcp-servers/mcp_server/<name>` is a legacy redirect to it). The new server
appears in the resources list with health "unknown", flipping to "healthy"
within ~10 seconds.

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
[`specs/mcp-gateway/quickstart.md`](../mcp-gateway/quickstart.md)
("Wire Coffer into your MCP client"), trigger a tool call (e.g. ask Claude
Code to read a file), then refresh the **Invocations** tab.

## 5. Activity and settings

- `/activity` — one page, one tab per record Coffer keeps: **Changes** (the
  audit log), **MCP calls** (every call the gateway proxied, across servers) and
  **Daemon** (what Coffer itself did, including what broke). Each tab filters by
  free text and time range plus the one filter its record affords; click any row
  to expand its raw underlying record, pretty-printed in a monospace, scrollable
  block. Both legacy URLs — `/audit` and `/observability` — resolve and redirect
  here. (Observability — system health / metrics — is a distinct surface
  reserved for the future, not this.)
- `/settings` — tabs sidebar opening on **General** (default rows-per-page, the
  preferred external editor), plus **Coffer's model** (at `/settings/engine` — its own
  LLM connection, and the switch and interval of each pass it runs unasked), **Data** (retention
  policy, manual prune), **Security** (where the master key lives) and **About**
  (version / license / source).

Some controls the v0 shell had are deliberately gone, and none of them came
back:

- There is no "Daemon" tab and no daemon-status panel. The daemon is an
  implementation detail; if it goes down, the daemon-offline banner is the one
  signal you see. (**Coffer's model** is not that panel — it configures the
  model Coffer itself runs on and its unattended passes, not the process.)
- There is no "Shutdown daemon" button — it would kill the very page you're on;
  use `coffer daemon stop` from the CLI.
- There is no "Rotate token" button — use `coffer daemon rotate-token`.

## Where things live

- Daemon state: `~/.coffer/coffer.db` and `~/.coffer/daemon.json`
  (unchanged from spec mcp-gateway).
- UI preferences: `localStorage` only — `coffer.language` (selected
  language) and `coffer.nav.collapsed` (sidebar mode).
- UI source: `frontend/src/` — see [`plan.md`](./plan.md) for the layout.
