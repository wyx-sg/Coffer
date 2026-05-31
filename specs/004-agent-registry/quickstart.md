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
location (`~/.claude` for Claude Code, `~/.codex` for Codex). In the desktop
app, the add/edit form offers a **folder picker** for choosing a custom config
directory instead of typing the path: the OS-native directory dialog in the
packaged app, and a daemon-backed folder browser on the web.

## Update an agent

```bash
coffer agent edit codex-work --config-dir /opt/codex-work-v2
```

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
`coffer agent add <type> ...` (or confirm it from the desktop Agents page).

## View an agent's config files

Each agent type exposes a curated set of its own config files. List them:

```bash
coffer agent config ls claude-code
coffer agent config ls claude-code --json
```

| Agent       | Keys                                             |
| ----------- | ------------------------------------------------ |
| Claude Code | `settings`, `settings_local`, `global`, `memory` |
| Codex       | `config`, `memory`                               |

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
recoverable. The desktop Config-files tab offers the same edit + save, plus an
in-editor find / replace convenience.

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
desktop Agents page. Restart your agent afterward to pick up Coffer's tools.

## What happens behind the scenes

- Each agent is stored as a Resource of kind `agent` in Coffer's SQLite
  database, identified by `agent:<name>`. The kind-agnostic Resource framework
  (introduced in spec 001) provides CRUD, validation, and audit.
- Audit events are recorded for every add / edit / remove and queryable from
  `coffer audit list`.
- The agent's `<config_dir>/skills` becomes the target directory used by future
  skill delivery (the 005-skill-manager spec).

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
