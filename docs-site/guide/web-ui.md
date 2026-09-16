# Web UI

Coffer includes a management UI for the whole vault. It lets you register and curate MCP
servers, deliver skills, browse and search knowledge, read what your agents have learned,
chat with them, keep the vault in step with a git remote, read everything Coffer recorded,
and adjust settings — all without touching the CLI.

## What the Web UI is

The Web UI is a React/Vite single-page application built on top of the daemon's REST API.
It is the primary visual surface for day-to-day work. The sidebar is organised into three
groups:

```
AGENTS
  Agents           manage your registered AI coding agents
  Chat             talk to one of them, streamed
RESOURCES
  MCP servers      manage your registered servers
  Skills           manage the skills Coffer can deliver to agents
  Knowledge        your collections, and the files in each
  Memory           what your agents have already learned
  Model providers  vendor endpoints and their keys
  Channels         the IM transports your agents answer on
SYSTEM
  Activity         what changed, what was called, what broke
  Sync             converge the vault with a git remote you own
  Settings
```

RESOURCES carries one entry per resource kind that has a list UI — six entries for six
such kinds. (The seventh, `agent`, is in AGENTS, because agents are the thing that *uses*
the vault rather than living in it.)

The **daemon serves the Web UI itself**, as static files at its own loopback origin, so the
page and the REST API are same-origin. There is nothing extra to install and no second
server to run: if the daemon is up, the UI is up. The **desktop app** is the same UI in a
native window — see [Download & install](/guide/install#desktop-app).

## Opening the Web UI

```bash
coffer open
```

`coffer open` reads the daemon's real port from `~/.coffer/daemon.json` and opens your
browser there. The address is stable across restarts: the daemon binds a **fixed** port,
`8000` by default, and refuses to start if it cannot have it rather than quietly moving
somewhere else. That is deliberate — your browser keys `localStorage` by origin, so a port
that drifted would silently reset the UI language, the sidebar state and the page size with
nothing to connect the two events. Pin a different one with `coffer daemon port set <n>`
and `coffer daemon restart`.

`coffer open` hands over no credential, because it does not need to: the daemon injects
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

If it refuses to start because something else holds its port, it says which process — either
free that port or move Coffer:

```bash
coffer daemon port show      # the port it wants, and the port it is on
coffer daemon port set 8123  # pin another one
coffer daemon restart        # apply it
```

`coffer daemon port` is the only surface for this setting, on purpose. It writes
`~/.coffer/daemon-config.json` directly and needs no running daemon — which matters,
because "no daemon is running" is exactly the state you have to fix a squatted port from.
There is no Settings panel for it: a port that is correct by default does not earn one.

## Opening the Web UI in development

From the repo root, run:

```bash
make dev
```

`make dev` starts two processes:

1. The Coffer daemon on its configured port (`8000` unless you pinned another), writing its
   address and token to `~/.coffer/daemon.json`.
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

The agent detail page has seven tabs:

- **Overview** — the agent's type and config directory, plus its LLM connection. On the
  built-in login the panel lists what the agent's own CLI offers, and the model pickers and
  the chat `/model` card offer exactly that — there is nothing to tick. For Claude Code
  that is its tier aliases (`opus`, `sonnet`, `haiku`, `fable`), each labelled with the
  model it resolves to today ("Opus 5"), because that is what the CLI's own picker offers
  and the only choice that cannot fail: which versioned models an account may run is a
  server-side fact with no copy on your machine. Your account's own extra options (a
  1M-context variant, say) come from the CLI's config file and appear alongside them. Codex
  answers with the models its own app-server reports.
- **Skills** — the skills Coffer manages for this agent, each with an enable/disable toggle.
  An **Install skills** button opens a picker dialog (search, filter, pagination,
  multi-select) to bind more skills to the agent.
- **MCP servers** — two sections. *Via Coffer gateway* shows the shim's install status and
  links to the MCP servers page. *Direct servers* lists the agent's own MCP entries, read
  from its config files: each row shows its source, transport, and enabled state as a plain
  badge, and the one write available is **Adopt** — pulling the entry into Coffer as a
  managed resource. Coffer does not edit another tool's private config, so there is no
  remove and no enable/disable toggle here.
- **Plugins** — the agent's *own* plugins, with an enable/disable switch and an uninstall.
  Coffer does not manage these, but it can see and toggle them, because a plugin is
  something running inside an agent Coffer is responsible for. Each write here touches a
  file Coffer does not own, so each is audited.
- **Conversations** — the agent's own transcripts, read off disk. A summary cache is warmed
  by a background pass, so the first visit is never the one that pays the cold read.
- **Memory** — what this agent reaches through the Coffer gateway (a link to the Memory
  page), its **Delivery** state, and a read-only table of the agent's OWN native
  per-project memory stores. Delivery is the one write here: install or remove Coffer's
  session-start hook in this agent's settings. The badge reads *Installed — never fired*
  until the hook has actually run once, because an installed hook that never fires is
  indistinguishable from no feature at all.
- **Config files** — open any of the agent's curated config files and edit it in place.
  Saving validates the file's format (malformed JSON/TOML is rejected and the file left
  unchanged), then writes atomically, keeping the previous contents as a `.bak` beside the
  file. A file that changed on disk mid-edit refuses the save and offers a reload, so a
  concurrent edit in your own editor is never silently overwritten.

An **Install Coffer MCP** toggle in the agent header writes (or removes) Coffer's own
`coffer` MCP-server entry into the agent's config, with a live status indicator.

### Chat

Open **Chat** to talk to one of your registered agents — Claude Code or Codex, driven by
Coffer with the whole vault behind them. There is no Coffer persona to talk to: the agents
answering here are the ones installed on your machine.

The page is a workspace rather than a document: a collapsible conversation list beside the
open thread, which collapses below `md` where two panes would leave the thread unreadable.
The open conversation **is the URL** (`/chat/:id`), so a reload or a shared link reopens the
same thread. Replies stream as they are produced, and a turn in flight can be interrupted.

These are the same conversations a [channel](/guide/channels) opens, whichever surface
started them — a thread begun from Telegram on your phone is here when you sit down.

### Skills

Open **Skills** to manage the skills Coffer can deliver to agents. The list is a table with
a search box, a filter, pagination, and row multi-select for bulk actions (such as bulk
verify or bulk remove). Import a skill from a local folder — a path picker, not a URL;
there is no Git fetcher and nothing to refresh from a remote. Verify a skill (which runs a
drift check) per row or in bulk, repair one that drifted, or remove one. Enabling or
disabling a skill for a specific agent happens on that **agent's** detail page, not here.

On the skill detail page, switch between tabs:

- **Overview** — metadata: source, version hash, master path, and timestamps.
- **Files** — the skill's master folder as a file tree, with an editor for each text file.
  The master folder is the source of truth and FOLDER-delivered skills are symlinked to it,
  so an edit reaches every agent without re-delivery. Binary files, and files too large to
  load whole, stay read-only — saving a partial read would truncate the file on disk.

### Knowledge

Open **Knowledge** to see your **collections**, each a row with its description and a file
count. **New collection** creates one; it asks for a name and a description and nothing
else, because there is nothing else to decide — a collection is a directory, and there is
no index over it to choose a shape for.

Clicking a collection opens `/knowledge/:collection`: a folder tree you walk a level at a
time with a filter box above it that matches names as you type (client-side, no button and
no request), the selected file rendered beside it, a search box over that collection, and
two buttons — **Upload** to convert a document into the tree, and **Tidy** to run the
[tidy pass](/guide/knowledge#the-tidy-pass) on demand.

There are no tabs, because there is no distinction left to tab between: an uploaded
document is converted to Markdown and filed as an ordinary knowledge file, with the same
frontmatter and the same place in the tree as one an agent typed. The original bytes are
kept in a hidden `.raw/`, and revisions the tidy pass superseded in a hidden `.history/`.

Nothing is built, rebuilt or kept fresh here. Search is `ripgrep` over the files
themselves, so a file you edited in your own editor, one an agent just wrote and one `git`
pulled in are all searchable the instant they land. Coffer used to embed these files and
rank retrieval by meaning; that was removed deliberately, and with it the reindex action
and the embedding settings that fed it.

The older `/knowledge-bases` and `/knowledge-bases/:name` URLs redirect here. `/memory` is
its own surface — see [Memory](#memory) below. The full picture, including the CLI and the
MCP tools, is in the [Knowledge guide](/guide/knowledge).

### Memory

Open **Memory** for what your agents have already learned, read out of their own native
memory — Claude Code's per-project notes, Codex's task groups — and normalised into facts
by project, plus one `global` partition for what is about *you* rather than any project.
The list is a table like every other one here: a row per partition showing the project it
was named from, how many facts it holds, and the same **reach** control the MCP-servers and
Skills lists carry per row, with multi-select for setting reach in bulk. Reach is one
button labelled with where the partition currently reaches — "Every agent", "2 agents",
"Disabled" — opening a panel where Disabled, Every agent and Only selected agents are the
choices: on or off, and for which agents. It is **this machine's** setting and is never
synced, so every machine you work on sets its own.

Nothing on this page is created by you, so the header action is **Read from agents**, not
Add — and not "Sync", because that name belongs to the [Sync](/guide/sync) page, which
converges the vault with a remote rather than reading anything out of an agent. Coffer
re-reads the agents on its own schedule; the button just does it now. A vault with no
partitions yet shows the same table with an empty row, and the button stays where it was.

Clicking a partition opens `/memory/:name`: the partition's own directory as a file tree
with a read-only preview beside it, its reach control, and an **Organise** pass that merges
duplicate facts, proposes supersessions and rewrites the partition's digest.

That is all there is, and the absence is deliberate. Per-fact actions — hide, pin, mark
superseded, settle a conflict — existed and were **removed**, along with the overrides
table that backed them. Those decisions only ever described Coffer's own *derived* copy,
which aggregation rewrites from the agents' native memory on its own schedule; a verdict
recorded against something regenerated behind your back is a promise the surface could not
keep. Coffer never writes back into an agent's own memory, so what is left is the truth it
can keep: here are the files, this is what they say, open one if you want to change it.

Two related surfaces live elsewhere on purpose:

- **Delivery** — whether Coffer's session-start hook is installed for an agent, and when it
  last actually fired — is on that **agent's** detail page, under its Memory tab. The hook
  is written into that one agent's own settings file, so it is per-agent state.
- **The audit trail** for memory events is on the [Activity](#activity) page's Changes tab,
  with the rest of the vault's. There is no second, memory-only copy of it.

### Model providers

Open `/model-providers` for the vendor endpoints Coffer holds keys for. A provider is
`{protocol, base_url, credential_ref}` — the endpoint and its key. The **model** is not
stored here and not chosen here: an agent's model is picked on its own detail page, and
Coffer's internal engine picks its own under **Settings → Engine**. Mark one provider
**internal default** and it becomes the connection that runs the unattended passes and
voice transcription.

This surface used to sit under Settings as "LLM connections". It moved because `provider`
is a resource kind like any other, and it was renamed because the old name described the
page rather than the thing it manages.

### Channels

Open `/channels` for the IM transports your agents answer on — Telegram and SeaTalk. Each
channel is registered with its credentials, paired with you through a single-use code, and
bound to a default agent. It used to sit under AGENTS; a channel is a credentialed
transport the vault owns, so it belongs with the other resources.

### Activity

Open `/activity` for everything Coffer recorded. One tab per record, each its
own newest-first table:

- **Changes** — the audit log: what changed in the vault, who changed it, when.
- **MCP calls** — every call the gateway proxied: server, capability, duration,
  outcome.
- **Daemon** — Coffer's own log: level, logger, message, including what broke.

Each tab filters by free text and time range, plus the one filter its record
affords — the actor, the call's status, errors only. Click any row to expand it
to its raw underlying record. A single server's calls are also on its own detail
page, under **Invocations** — the same table, scoped to that server.

They are three tables rather than one because one table could only show what all
three records have in common, and that is not much: a call's duration and a log
record's level would have had nowhere to go. Reading *across* the three is your
agent's job, not a filter's: **`coffer__diagnose`** returns all of them already
joined on one timeline, so "why did that fail?" is a question you can just ask.

For scripting, `GET /api/v1/audit` and `coffer audit` are unchanged. `/audit` and
`/observability` redirect here.

### Sync

Open `/sync` to converge this vault with a git remote you own. It is a top-level page under
SYSTEM rather than a Settings tab, because convergence is something you open deliberately
rather than a setting you tweak once — `/settings/sync` redirects here.

Three tabs, and the active one lives in the URL (`?tab=`) so a link can land on History:

- **Status** — the configured remote, the master key, and anything waiting on you.
- **History** — every round this machine has run. Status answers "what is it doing";
  History answers "what has it been doing", which one round's worth of prose never could.
- **Machines** — the registry of machines converging on this remote.

Conflicts and held rounds appear as **banners on Status**, not as a tab of their own: they
are states the vault passes through, and a permanent tab would read as a place you are
meant to visit. The full picture — what converges, what stays local, and how the master key
travels — is in the [Sync guide](/guide/sync).

### Settings

Open `/settings` for five tabs: **General**, **Engine**, **Data** (retention policy, manual
prune), **Security** (master-key storage) and **About** (version, license, source). Sync is
not among them — it is a top-level page of its own under SYSTEM.

**Engine** is where Coffer's own machinery is configured, as opposed to anything served to
an agent. Two cards:

- **Internal engine** — which provider connection and model Coffer's own passes run on.
- **Upkeep** — the work Coffer does when nobody asked. Three passes run on a timer, each
  with its own switch and interval: **aggregate** reads the agents' native memory into the
  derived tree, **organise** lets the model rewrite that derived digest, and **tidy** lets
  it rewrite your own knowledge files. Each row says what its pass actually *writes*,
  because that is the difference that matters: two rewrite derived files that deleting and
  re-running reproduces, and one rewrites the only copy — that last one is the only row
  carrying a warning. Something that rewrites your files on a timer should be something you
  can see and stop, which is why the card exists. Edits auto-save, like every settings
  surface here. What the passes are doing right now is also readable from
  `GET /api/v1/upkeep/runs`.

There is no "Daemon" tab and no daemon-status panel — the daemon is an implementation
detail surfaced only by the offline banner when something goes wrong, and its one setting
(the port) is a CLI-only concern by design.

### Language

Switch between English and 中文 from the language switcher at the bottom of the sidebar.
The change takes effect immediately and persists in `localStorage` under `coffer.language`.

## Next steps

- [Register an MCP server →](/guide/register-server)
- [Download & install →](/guide/install)
