# Web UI

Coffer includes a browser-based management UI for the gateway. It lets you add, edit,
enable, and disable MCP servers; browse the audit and invocation log; and adjust settings
— all without touching the CLI.

## What the Web UI is

The Web UI is a React/Vite single-page application built on top of the daemon's REST API.
It is the primary visual surface for day-to-day MCP gateway work. The sidebar is organised
into two groups:

```
RESOURCES
  MCP servers      manage your registered servers
  Agents           manage your registered AI coding agents
SYSTEM
  Observability    audit and invocation log
  Settings
```

For end users, the Web UI ships **embedded inside the [Desktop app](/guide/desktop)** — no
separate install or server to run. For developers working from a checkout, it runs as a Vite
dev server (see below).

## Opening the Web UI in development

From the repo root, run:

```bash
make dev
```

`make dev` starts two processes:

1. The Coffer daemon (`coffer daemon start`) on a free port in the range 8000–8009, writing
   its address and token to `~/.coffer/daemon.json`.
2. The Vite dev server at **`http://localhost:5173/`**. A dev-only token-injection plugin
   (`frontend/vite.config.ts`) reads `~/.coffer/daemon.json` and injects the daemon token
   into the page automatically — you do not need to paste anything by hand.

Vite only starts once the daemon is confirmed reachable (up to 30 seconds). Open
`http://localhost:5173/` in any modern browser.

> **End users:** the Web UI is bundled inside the Desktop app. See the
> [Desktop app guide](/guide/desktop) for installation instructions.

## What you can do

### First-run welcome

The first time you open the UI with no servers registered, the Resources page shows a
welcome card with a short pitch and one primary action: **Add MCP server**. There is no
empty table or placeholder row.

If the daemon is not running, the UI shows a "Daemon not running" view with a copyable
`coffer daemon start` command instead. The view recovers automatically once the daemon
becomes reachable — no manual reload needed.

### MCP servers (Resources)

Click **Add MCP server** to open the import dialog. Paste the standard `mcpServers` JSON
block from any vendor's README — one server or many at once:

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

A review step lets you mark which `env` values are secrets; those are written to the OS
keychain rather than stored in the resource config.

On the server detail page, switch between tabs:

- **Overview** — health, last seen, transport, namespace.
- **Tools / Resources / Prompts** — one row per capability with an enabled/disabled toggle
  and a search box to narrow the list.
- **Invocations** — a paged table of per-call timestamp, type, capability, status, and
  latency. Click any row to expand its raw invocation JSON.

### Agents

Open **Agents** to manage your registered AI coding agents (`claude_code` and `codex`).
Click **Detect** to scan for installed agents; the detect dialog lists what was found and
you confirm each one before it is registered — nothing is registered automatically.

The agent detail page lets you open any of the agent's curated config files in an editor.
Saving validates the file's format (malformed JSON/TOML is rejected and the file left
unchanged), writes atomically with a `.bak` backup, and offers a find/replace box that
scrolls to the match. An **Install Coffer MCP** toggle writes (or removes) Coffer's own
`coffer` MCP-server entry into the agent's config, with a live status indicator. A folder
picker sets the agent's skill directory.

### Observability

Open `/observability` to see the audit log — every lifecycle event (server added, tool
enabled, etc.) as a plain-language activity line. Filter by time range and actor; click any
row to expand its raw log JSON. The legacy `/audit` URL redirects here.

### Settings

Open `/settings` for **Data** (retention policy, manual prune, backups) and **About**
(version, license, source). There is no "Daemon" tab and no daemon-status panel — the
daemon is an implementation detail surfaced only by the offline banner when something goes
wrong.

### Language

Switch between English and 中文 from the language switcher at the bottom of the sidebar.
The change takes effect immediately and persists in `localStorage` under `coffer.language`.

## Next steps

- [Register an MCP server →](/guide/register-server)
- [Desktop app →](/guide/desktop)
