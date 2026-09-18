# Quickstart — Coffer Agent Registry

Once Coffer has finished its first-run setup, the Agent Registry lets you tell
Coffer which AI agents are installed on your machine so later features
(skills, memory, knowledge bases) know where to deliver assets.

## Discover installed agents

Coffer never registers an agent silently. Instead it offers a read-only scan
that reports the agents it finds installed but not yet registered as
**candidates**; you review them and confirm which to add:

| Agent type   | Detection marker |
| ------------ | ---------------- |
| Claude Code  | `~/.claude/`     |
| OpenAI Codex | `~/.codex/`      |

Each type covers both the product's CLI and its app/IDE form, since they share
one config directory (`~/.claude/` for Claude Code, `~/.codex/` for Codex).

Open the Agents page and run discovery (or run `coffer agent detect`) to see the
candidates. Confirm a candidate to register it — Coffer fills in the type's
default config directory and a suggested name for you. Nothing is registered, and
nothing is changed on disk, until you confirm.

## List your agents

```bash
coffer agent list
```

JSON for scripts:

```bash
coffer agent list --json
```

One agent's registered name, type and config dir:

```bash
coffer agent show claude-code
coffer agent show claude-code --json
```

## Manually add an agent (custom path)

If your agent is installed somewhere non-standard, add it with an explicit
config directory:

```bash
coffer agent add codex --name codex-work --config-dir /opt/codex-work
```

Coffer auto-creates the `<config-dir>/skills` subdirectory (where skills are
delivered), then validates that the resolved path exists, is a directory, is
writable by your user, and is not a privileged system location. Failures are
reported with the specific reason. The supported types are `claude_code` and
`codex`.

The name is optional — omit `--name` and Coffer derives a stable per-type
default (underscores become hyphens, e.g. `claude_code` → `claude-code`).
`--config-dir` is optional too — omit it and Coffer uses the type's standard
location (`~/.claude` for Claude Code, `~/.codex` for Codex). In the web UI,
the add/edit form offers a **folder picker** for choosing a custom config
directory instead of typing the path: the host's native directory dialog opened
through the daemon, falling back to a daemon-backed folder browser.

## Update an agent

```bash
coffer agent edit codex-work --config-dir /opt/codex-work-v2
```

`edit` is also where the model an agent answers with is bound — the binding
lives on the agent, not on the connection (FR-031):

```bash
coffer agent edit codex-work --model gpt-5-codex
coffer agent edit claude-code --model claude-opus-5 --fast-model claude-haiku-4-5
coffer agent edit claude-code --clear-fast-model       # unbind the fast slot
coffer agent show codex-work                           # read the binding back
```

An unbound agent projects no model at all and runs on its own default, which is
why clearing a slot needs its own flag rather than an empty string. The change
reaches the agent's config file the next time its connection is activated
(`coffer provider switch <name>`) — that is the step that writes native config.

## Remove an agent

```bash
coffer agent rm codex-work
```

Removal is not permanent — Coffer keeps no "suppression" list. If the agent is
still installed, it simply re-appears as a discovery candidate on the next scan,
so an accidental removal is easy to undo with one confirm.

## Discover agents again

To scan for installed-but-unregistered agents (for example after installing a
new agent), run discovery again:

```bash
coffer agent detect
```

This lists the candidates read-only; it registers nothing. Add one with
`coffer agent add <type> ...` (or confirm it from the web Agents page).

## View an agent's config files

Each agent type exposes a curated set of its own config files. List them:

```bash
coffer agent config ls claude-code
coffer agent config ls claude-code --json
```

| Agent       | Keys                                                                |
| ----------- | ------------------------------------------------------------------- |
| Claude Code | `settings`, `settings_local`, `global`, `instructions`, `subagents` |
| Codex       | `config`, `instructions`, `hooks`                                   |

(`instructions` is the human-authored instructions file — `CLAUDE.md` /
`AGENTS.md`. `subagents` is a **directory** entry; see "Edit directory config
entries" below.)

Print one file's content:

```bash
coffer agent config cat claude-code settings
```

Edit one. With no `--from-file`, this opens the file's current content in your
`$EDITOR`; on save, Coffer writes the edited content back:

```bash
coffer agent config edit claude-code settings
```

Or save content non-interactively from a file:

```bash
coffer agent config edit claude-code settings --from-file ./new-settings.json
```

On save, Coffer validates the content against the file's format (malformed
`json`/`toml` is rejected and the on-disk file is left unchanged), writes it
atomically, and keeps a `.bak` of the prior version so a bad edit is
recoverable. If the file changed on disk since you read it, the save is
rejected and the editor offers a reload instead of silently overwriting. The
Config-files tab offers the same save from the web UI: a file opens in a viewer
that becomes **editable behind an explicit Edit**, and an unsaved draft is
guarded three ways — picking another file, leaving the tab, and leaving the page
each ask first. Beside the content it also offers open-in-external-editor /
reveal-in-file-manager for the file and its containing folder, for the edits you
would rather make in your own editor (Coffer uses your "preferred external
editor" preference from Settings).

## Edit directory config entries

Some config entries are directories of files rather than a single file —
Claude Code's `subagents` entry (`~/.claude/agents/`, one Markdown file per
personal subagent). List, write, and delete individual child files:

```bash
coffer agent config files claude-code subagents          # list child files
coffer agent config write claude-code subagents reviewer.md --from-file ./reviewer.md
echo "..." | coffer agent config write claude-code subagents reviewer.md
coffer agent config rm claude-code subagents reviewer.md
```

Child paths are validated before any disk access (no `..`, no absolute paths,
`.md` only); writes create the file if needed and keep the same atomic + `.bak`
safety net; deletes preserve the prior content as `.bak`.

## View and adopt an agent's own MCP entries

Beyond Coffer's one-click entry, the MCP tab (and CLI) shows every MCP server
configured in the agent's own files — derived live from the files, never
copied:

```bash
coffer agent mcp entries claude-code
coffer agent mcp entries claude-code --json
```

Each entry shows its name, source file, transport, the `enabled` flag where
the format has one (Codex), and whether an equivalent `mcp_server` resource is
already registered in Coffer. Env/header values never leave the daemon — only
key names are listed.

Coffer offers two writes here: **remove** and **adopt**. Flipping a Codex
`enabled` flag is not one of them — that switch belongs to the agent's own UI.

```bash
coffer agent mcp remove-entry claude-code my-server
coffer agent mcp remove-entry claude-code my-server --source settings  # when both files carry the name
```

Removal edits only that entry's source file, keeps a `.bak`, and refuses to
touch Coffer's own `coffer` entry (that one is `coffer agent mcp
install|uninstall`).

**Adopt** a direct entry into Coffer to serve it to all agents through the
gateway instead. Secret-looking env/header keys must be mapped to credential
references — Coffer stores the value as Fernet ciphertext in its encrypted
credential store ([Envelope-Encrypted Credentials](../../docs/decisions/envelope-encrypted-credential-store.md));
plaintext never reaches the database, logs, or audit:

```bash
coffer agent mcp adopt claude-code my-server --secret API_KEY=coffer/mcp/my-server/api_key
```

Coffer registers the `mcp_server` resource, verifies it reads back, and only
then removes the entry from the agent's file; any failure rolls back so you
never lose a working entry. On a name conflict the error suggests an
alternative — retry with `--name <suggested>`.

## Manage an agent's plugins

The agent's **Plugins** tab — and the CLI — lists every installed plugin in one
table, with the marketplace it came from as a column:

```bash
coffer agent plugin list codex
coffer agent plugin list codex --json
```

Each plugin shows its `<name>@<marketplace>` id, enabled state, and whether its
on-disk cache is present. Two writes are offered:

```bash
coffer agent plugin enable codex fmt@acme
coffer agent plugin disable codex fmt@acme
coffer agent plugin uninstall codex fmt@acme        # asks first; --force skips
```

Both touch only the documented surface — Codex's `config.toml` entry, Claude
Code's `enabledPlugins` map in `settings.json`. An uninstall for Codex also
deletes the plugin's cache directory; for Claude Code it shells out to `claude
plugin uninstall`, so Coffer never hand-writes that agent's internal inventory —
and when the `claude` CLI is not on `PATH` the listing reports
`can_uninstall=false` and the affordance is hidden. Installing plugins and
managing marketplaces stay with the agent's own tooling.

## Read the agent's own memory

The agent's **Memory** tab shows three things: a pointer to Coffer's own Memory
page, the per-agent memory **delivery** switch (owned by spec memory), and the
coding agent's OWN native memory stores, read-only. The stores are also on the
CLI:

```bash
coffer agent native-memory claude-code                 # one row per store
coffer agent native-memory-files claude-code --dir <memory_dir>
coffer agent native-memory-files claude-code --dir <memory_dir> --path MEMORY.md
```

`--dir` takes a `memory_dir` the scan handed out and nothing else: any other
path under the agent's config dir is a 404. Coffer never writes an agent's own
memory — the surface previews a file and offers open / reveal instead of an
editor.

## Browse the agent's own conversations

The **Conversations** tab lists the agent's local session transcripts, searchable
and sortable, and opens one as a readable conversation beside a contents list of
the person's own prompts. On the CLI:

```bash
coffer agent transcripts claude-code --query refactor --sort last_activity_at --order desc
coffer agent transcript claude-code --path <source_path> --limit 200
```

The listing carries no message text; a body travels only through the
single-session read, secret-scrubbed, capped per turn and paged. Nothing is
written and nothing is retained — a cold parse may just be slower than a warm
one.

## See what an agent can be put on

```bash
curl -s -H "X-Coffer-Token: $COFFER_TOKEN" \
  http://127.0.0.1:8000/api/v1/agent-providers/claude_code/models | jq
```

```json
{
  "models": [
    {
      "id": "opus",
      "label": "Claude Opus 5",
      "description": "Most capable",
      "efforts": ["low", "medium", "high"],
      "default_effort": null
    }
  ]
}
```

Every entry is read back from the installed agent on the spot — Coffer writes no
model list down anywhere, so a model released after Coffer shipped shows up
without a Coffer release (FR-032/FR-033). Where an entry comes from is per
type: see `agent-registry/claude-code` and `agent-registry/codex`. If one source
is unavailable — the CLI is not installed, the agent is not signed in — you lose
exactly that source's entries and the request still succeeds. The reasoning
levels travel beside the id, never folded into it, so a model with four levels
is still one row (FR-036); an agent whose runtime publishes no default reports
`null` rather than guessing one (FR-038).

## Install Coffer's MCP into an agent

Wire Coffer's aggregated MCP server into an agent in one command:

```bash
coffer agent mcp status claude-code      # installed? false
coffer agent mcp install claude-code     # writes the `coffer` stdio entry
coffer agent mcp status claude-code      # installed? true
coffer agent mcp uninstall claude-code   # removes it
```

`install` writes a `coffer` entry into the agent's MCP config
(`~/.claude.json` for Claude Code, `~/.codex/config.toml` for Codex) pointing
at the absolute path of `coffer-mcp-shim`. It is idempotent, backs up the
prior config to `.bak`, and is also available as a one-click button on the
web Agents page. Restart your agent afterward to pick up Coffer's tools.

## What happens behind the scenes

- Each agent is stored as a Resource of kind `agent` in Coffer's SQLite
  database, identified by an immutable `uid`; its name is a label you can
  change. The kind-agnostic Resource framework
  (spec resource-framework) provides CRUD, validation, and audit.
- Audit events are recorded for every add / edit / remove and queryable from
  `coffer audit list`.
- The agent's `<config_dir>/skills` becomes the target directory used by future
  skill delivery (the skill-manager spec).

## Troubleshooting

**"Default config_dir is not writable"** — your install lives somewhere your
user can't write to. Either fix permissions on the path or pass
`--config-dir <writable-path>` when adding the agent.

**Registered an agent I don't want** — `coffer agent rm <name>`. It will still
show up as a discovery candidate while it's installed, but it stays out of your
registry until you confirm it again.

**Discovery missed an installed agent** — your install is in a non-standard
location, so its marker isn't where Coffer looks. Add it explicitly with
`coffer agent add <type> --config-dir <your-path>`.
