# Web UI

Coffer includes a browser-based management UI for the gateway. It lets you add, edit,
enable, and disable MCP servers; browse the invocation log; and adjust settings
— all without touching the CLI.

## What the Web UI is

The Web UI is a React/Vite single-page application built on top of the daemon's REST API.
It is the primary visual surface for day-to-day MCP gateway work. The sidebar is organised
into three groups:

```
AGENTS
  Agents           manage your registered AI coding agents
RESOURCES
  MCP servers      manage your registered servers
  Skills           manage the skills Coffer can deliver to agents
  Knowledge        one page per knowledge scope: notes and documents
  Model providers  vendor endpoints and their keys
  Channels         the IM transports your agents answer on
SYSTEM
  Settings
```

RESOURCES carries one entry per resource kind that has a list UI — five kinds,
five entries. AGENTS carries one, because agents are the thing that *uses* the
vault rather than living in it.

The **daemon serves the Web UI itself**, as static files at its own loopback origin, so the
page and the REST API are same-origin. There is nothing extra to install and no second
server to run: if the daemon is up, the UI is up.

## Opening the Web UI

```bash
coffer open
```

`coffer open` reads the daemon's real port from `~/.coffer/daemon.json` — the daemon binds
the first free port in its range, so the address moves between restarts — and opens your
browser there. It hands over no credential, because it does not need to: the daemon injects
its current API token into the `index.html` it serves, so **any** page the daemon serves is
already signed in. A bookmark, a typed address, a reload, or a deep link like
`http://127.0.0.1:<port>/agents` all work the same way, including after the daemon has been
restarted and minted a new token.

The token is never put in a URL — that would write it into your browser history — and it is
never stored in the browser either. A stored token would outlive the daemon that minted it,
which is exactly how a reload used to end in "not authenticated" with no way out but
re-running `coffer open`.

For that page-served token to be safe, the daemon answers only requests addressed to its own
loopback address: a request whose `Host` header says anything else is refused with
`421`. That is what stops a malicious web page from re-pointing its own hostname at
`127.0.0.1` and reading the token out of the served page.

If the daemon is not running, start it first:

```bash
coffer daemon start
coffer open
```

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

> The dev server is a different origin from the daemon, so it needs the cross-origin
> opt-in: `make dev` sets `COFFER_DEV_CORS=1` for you. Everyday use goes through
> `coffer open`, which is same-origin and needs no opt-in.

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

A review step lets you mark which `env` values are secrets; those are encrypted into
Coffer's credential store (only their refs are kept in the resource config) rather than
stored as plaintext in the resource config.

On the server detail page, switch between tabs:

- **Overview** — health, last seen, transport, namespace.
- **Tools / Resources / Prompts** — one row per capability with an enabled/disabled toggle
  and a search box to narrow the list.
- **Invocations** — a paged table of per-call timestamp, type, capability, status, and
  latency. Click any row to expand its raw invocation JSON.

### Agents

Open **Agents** to manage your registered AI coding agents (`claude_code` and `codex`).
The list is a table with a search box, a status filter, pagination, and row multi-select
for bulk actions. Click **Detect** to scan for installed agents; the detect dialog lists
what was found and you confirm each one before it is registered — nothing is registered
automatically. Each agent is registered against a single **config directory** (for example
`~/.claude` or `~/.codex`); Coffer delivers skills into that directory's `skills/` subfolder.

The agent detail page has four tabs:

- **Overview** — the agent's type and config directory, plus its LLM connection. On the
  built-in login the panel lists the models the agent's own CLI reports, each with a
  checkbox. Tick the ones your account can actually run and only those are offered in the
  model pickers and the chat `/model` card; tick none and all of them are, which is how a
  fresh install behaves. Coffer cannot work this out for you — which models an account may
  run is a server-side fact with no copy on your machine, and the CLI's catalogue lists
  every model the installed release has ever known. Models the CLI itself marks as retired
  are dropped before you ever see them.
- **Skills** — the skills Coffer manages for this agent, each with an enable/disable toggle.
  An **Install skills** button opens a picker dialog (search, filter, pagination,
  multi-select) to bind more skills to the agent.
- **MCP servers** — two sections. *Via Coffer gateway* shows the shim's install status and
  links to the MCP servers page. *Direct servers* lists the agent's own MCP entries, read
  from its config files: each row shows its source, transport, and enabled state as a plain
  badge, and the one write available is **Adopt** — pulling the entry into Coffer as a
  managed resource. Coffer does not edit another tool's private config, so there is no
  remove and no enable/disable toggle here.
- **Config files** — open any of the agent's curated config files and edit it in place.
  Saving validates the file's format (malformed JSON/TOML is rejected and the file left
  unchanged), then writes atomically, keeping the previous contents as a `.bak` beside the
  file. A file that changed on disk mid-edit refuses the save and offers a reload, so a
  concurrent edit in your own editor is never silently overwritten.

An **Install Coffer MCP** toggle in the agent header writes (or removes) Coffer's own
`coffer` MCP-server entry into the agent's config, with a live status indicator.

### Skills

Open **Skills** to manage the skills Coffer can deliver to agents. The list is a table with
a search box, a filter, pagination, and row multi-select for bulk actions (such as bulk
verify or bulk remove). Import a skill from a local folder or fetch one from a public Git
URL; verify a skill (which runs a drift check) per row or in bulk; refresh a Git-sourced
skill; or remove one. Enabling or disabling a skill for a specific agent happens on that
**agent's** detail page, not here.

On the skill detail page, switch between tabs:

- **Overview** — metadata: source, version hash, master path, and timestamps.
- **Files** — the skill's master folder as a file tree, with an editor for each text file.
  The master folder is the source of truth and FOLDER-delivered skills are symlinked to it,
  so an edit reaches every agent without re-delivery. Binary files, and files too large to
  load whole, stay read-only — saving a partial read would truncate the file on disk.

### Knowledge

Open **Knowledge** to see your knowledge scopes: `global`, one per project, and any
collection you created. Each row shows note and document counts and disk usage.
**Add collection** creates a named one; it asks for nothing beyond a name and a
description, because which index a scope carries is an implementation detail rather than a
question to put to you at creation time. The embedding model itself is configured once
under **Settings → Embedding**, not per scope.

Clicking a scope opens `/knowledge/:scope` with two tabs, and a filter box above the tree
that matches filenames as you type — client-side, no button and no request:

- **Documents** — files ingested and converted to Markdown. Drag files in, read one,
  re-run conversion, or delete. Documents that track an external original show whether
  that original has changed on disk.
- **Notes** — what agents (and you) wrote down. Add, edit, and delete notes here.

The header carries the scope title, a rename pencil and the project path. **Upload** and
**Tidy** are the two buttons — Tidy runs the tidy pass over `notes/` on demand — with
Settings, Check sources and Reindex behind an overflow menu. A warning appears beside the
title only when the scope holds documents that failed to convert.

Searching the server is not on this page: agents use `coffer__search` and the CLI has
`coffer knowledge recall`.

The older `/memory`, `/memory/:name`, `/knowledge-bases`, and `/knowledge-bases/:name` URLs
redirect here.

### Model providers

Open `/model-providers` for the vendor endpoints Coffer holds keys for. A provider is
`{protocol, base_url, credential_ref}` — the endpoint and its key. The **model** is not
stored here and not chosen here: an agent's model is picked on its own detail page, and
Coffer's internal engine picks its own below. Mark one provider **internal default** and
it becomes the connection that runs the knowledge tidy pass and voice
transcription. The embedding configuration is a card at the bottom of the same page.

This surface used to sit under Settings as "LLM connections". It moved because `provider`
is a resource kind like any other, and it was renamed because the old name described the
page rather than the thing it manages.

### Channels

Open `/channels` for the IM transports your agents answer on — Telegram and SeaTalk. Each
channel is registered with its credentials, paired with you through a single-use code, and
bound to a default agent. It used to sit under AGENTS; a channel is a credentialed
transport the vault owns, so it belongs with the other resources.

### Audit log

There is no audit-log page. `/audit` is not routed and nothing in the sidebar links to it.

In practice nobody opened it. A person does not sit down to browse "what changed in my vault" — they notice something is broken and ask whoever is helping them, which is an agent. So the log kept its reader and lost its page.

An agent reads it with **`coffer__diagnose`**, which returns both records at once — the audit log (what changed, and who changed it) and the daemon's own log (what happened, including failures) — on one newest-first timeline. Ask your agent "why did that fail?" and it has the tool in hand.

For scripting, `GET /api/v1/audit` and `coffer audit` are unchanged.

### Settings

Open `/settings` for **General**, **Data** (retention policy, manual prune), **Sync**
(vault export and import), **Security** and **About** (version, license, source). There is no "Daemon" tab and no daemon-status panel — the
daemon is an implementation detail surfaced only by the offline banner when something goes
wrong.

### Language

Switch between English and 中文 from the language switcher at the bottom of the sidebar.
The change takes effect immediately and persists in `localStorage` under `coffer.language`.

## Next steps

- [Register an MCP server →](/guide/register-server)
- [Download & install →](/guide/install)
