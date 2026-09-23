# Agents

An **agent** is a registered local AI coding agent that Coffer can manage — its config files and its connection to Coffer's own MCP server. Two agent types ship today: `claude_code` and `codex`.

Coffer never registers an agent automatically. It can **detect** the agents installed on your machine, but you confirm each one before it is registered.

## Detect & register

Run detection to discover installed agents, then register the ones you want:

```bash
coffer agent detect            # → claude_code (detected), codex (detected)
coffer agent add claude_code   # register; --name defaults to claude-code
coffer agent add codex --name my-codex --config-dir ~/.codex --description "work laptop"

coffer agent list              # → claude-code | claude_code | registered
```

- `coffer agent detect` scans for installed agents and reports what it finds. Nothing is registered by this step — it is discovery only.
- `coffer agent add <type>` registers an agent. `<type>` is `claude_code` or `codex`. `--name` is optional and defaults to a per-type name (for example, `claude_code` → `claude-code`). Optional flags: `--config-dir PATH` (the agent's config directory — defaults to the type's standard location, e.g. `~/.claude`; Coffer delivers skills into that directory's `skills/` subfolder) and `--description TEXT`.
- `coffer agent list` shows all registered agents with their type and status.
- `coffer agent show <name>` prints a registered agent's details; `coffer agent rm <name>` removes it.

Every other `coffer agent` command addresses an agent by the **name** you registered it under. The daemon identifies an agent by an immutable uid, so the CLI looks the name up once and exits with a not-found error if no agent carries it; renaming an agent never breaks what refers to it.

Detection looks for each type's config directory:

| Type          | Detected when this exists |
| ------------- | ------------------------- |
| `claude_code` | `~/.claude/`              |
| `codex`       | `~/.codex/`               |

Each type covers both the product's CLI and its app/IDE form, since they share that directory. An install in a non-standard location is not detected; register it with `--config-dir`.

`--config-dir` must be an existing directory, writable by you and not under a privileged system location, or registration fails with the specific reason. Coffer never creates the config directory itself — a mistyped path would otherwise receive skills the agent never reads — but it does create the `skills/` subfolder inside it. In the web UI the add and edit forms offer a folder picker instead of a typed path.

Change a registered agent's fields with `edit`:

```bash
coffer agent edit my-codex --config-dir ~/work/.codex --description "work profile"
```

`edit` also binds the model an agent answers with (`--model`, `--fast-model`, `--clear-fast-model`, `--wire-api`) — see [Model providers](/guide/providers).

Removing an agent is not permanent. Coffer keeps no suppression list, so an agent that is still installed is offered again by the next `coffer agent detect`, and one confirmation brings it back.

## Edit config files

Each agent exposes a curated set of config files, addressed by a short **key**:

| Type          | Key              | File                                                 |
| ------------- | ---------------- | ---------------------------------------------------- |
| `claude_code` | `settings`       | `~/.claude/settings.json`                            |
| `claude_code` | `settings_local` | `~/.claude/settings.local.json`                      |
| `claude_code` | `global`         | `~/.claude.json` (also holds user-scope MCP servers) |
| `claude_code` | `instructions`   | `~/.claude/CLAUDE.md`                                |
| `claude_code` | `subagents`      | `~/.claude/agents/` (a directory — see below)        |
| `codex`       | `config`         | `~/.codex/config.toml`                               |
| `codex`       | `instructions`   | `~/.codex/AGENTS.md`                                 |
| `codex`       | `hooks`          | `~/.codex/hooks.json`                                |

List the keys for an agent, print one, or edit one:

```bash
coffer agent config ls claude-code              # list the curated files + which exist
coffer agent config cat claude-code settings    # print ~/.claude/settings.json
coffer agent config edit claude-code settings   # open in your editor
coffer agent config edit claude-code settings --from-file ./settings.json
```

Writes go through the same safeguards on every surface:

- **Format validation** — JSON and TOML files are parsed before writing. A malformed payload is rejected and the file on disk is left unchanged.
- **Atomic write** with a `.bak` backup — the previous contents are preserved next to the file.
- **Allowlisted, not-yet-created files** are listed too. Opening one that does not exist yet shows it as empty; reading it does **not** create the file.

A **directory** entry such as `subagents` holds one Markdown file per item. List, write and delete its child files individually:

```bash
coffer agent config files claude-code subagents                  # list child files
coffer agent config write claude-code subagents reviewer.md --from-file ./reviewer.md
echo "..." | coffer agent config write claude-code subagents reviewer.md
coffer agent config rm claude-code subagents reviewer.md
```

A child path must be relative, stay inside the directory, and end in `.md`; it is checked before anything touches disk. Writes and deletes keep the same atomic write and `.bak` backup.

## Install Coffer's MCP server

A single command writes (or removes) Coffer's own MCP server entry — a `coffer` stdio entry pointing at the `coffer-mcp-shim` binary — into an agent's config:

```bash
coffer agent mcp status claude-code      # → not installed / installed
coffer agent mcp install claude-code     # write the coffer entry
coffer agent mcp uninstall claude-code   # remove it
```

Install is idempotent: running it again updates the existing entry in place rather than duplicating it. The entry goes into `~/.claude.json` for Claude Code and `~/.codex/config.toml` for Codex, with a `.bak` of the prior file, and its command is the shim's absolute path, so an agent launched without your shell's `PATH` still finds it. Restart the agent afterwards to pick up Coffer's tools. Once installed, the agent reaches every server you have registered with Coffer through the shim — see [Connect a client](/guide/connect-client).

## The agent's own MCP entries

Besides Coffer's own `coffer` entry, an agent may have MCP servers configured directly in its files. Coffer lists them live from those files and keeps no copy:

```bash
coffer agent mcp entries claude-code
coffer agent mcp entries claude-code --json
```

Each entry shows its name, source file, transport, the `enabled` flag where the format has one (Codex), and whether an equivalent `mcp_server` is already registered in Coffer. Environment and header values never leave the daemon — only their key names are listed.

Two writes are offered, **remove** and **adopt**:

```bash
coffer agent mcp remove-entry claude-code my-server
coffer agent mcp remove-entry claude-code my-server --source settings   # when both files carry the name
coffer agent mcp adopt claude-code my-server --secret API_KEY=my-server-api-key
```

- **Remove** edits only the entry's source file, keeps a `.bak`, and refuses Coffer's own `coffer` entry — that one is `coffer agent mcp install|uninstall`.
- **Adopt** moves the entry into Coffer as a registered `mcp_server`, so every agent reaches it through the gateway instead of one agent alone. Each env or header key whose name looks like a secret (containing `TOKEN`, `SECRET`, `PASSWORD`, `API_KEY`, `CREDENTIAL` or `AUTHORIZATION`) needs a `--secret KEY=CREDENTIAL_REF` mapping, or the adopt is refused with the unmapped keys listed; the value is stored in Coffer's encrypted credential store (see [Credentials](/guide/credentials)) and the resource keeps only the reference. Coffer registers the server and checks it reads back **before** removing the entry from the agent's file, and rolls back on any failure, so you never lose a working entry. On a name clash the error suggests an alternative — retry with `--name <suggested>`.

Toggling an entry's `enabled` flag is left to the agent's own UI.

## The agent's own plugins

Both agent types install plugins of their own from marketplaces. Coffer does not install plugins or manage marketplaces, but it lists them and can switch one on or off or uninstall it, because a plugin is a thing running inside an agent Coffer is responsible for:

```bash
coffer agent plugin list codex                   # id, marketplace, enabled, cache present
coffer agent plugin enable codex fmt@acme
coffer agent plugin disable codex fmt@acme
coffer agent plugin uninstall codex fmt@acme     # asks first; --force skips
```

A plugin is addressed as `<name>@<marketplace>`. Enable and disable touch only the documented switch — `enabledPlugins` in Claude Code's `settings.json`, the plugin's entry in Codex's `config.toml`. Uninstall differs by type: for Codex, Coffer removes the config entry and the plugin's cache directory; for Claude Code it runs `claude plugin uninstall`, so Coffer never hand-writes Claude Code's internal plugin inventory. When the `claude` CLI is not on `PATH`, the listing reports the plugin as not uninstallable and the web UI hides the action.

Each of these writes a file Coffer does not own, so each is audited (`agent_plugin_toggled`, `agent_plugin_uninstalled`).

## The agent's own memory and conversations

Coffer reads — never writes — an agent's native memory stores and its recorded session transcripts:

```bash
coffer agent native-memory claude-code                                  # one row per store
coffer agent native-memory-files claude-code --dir <memory_dir>         # a store's files
coffer agent native-memory-files claude-code --dir <memory_dir> --path MEMORY.md

coffer agent transcripts claude-code --query refactor --sort last_activity_at --order desc
coffer agent transcript claude-code --path <source_path> --limit 200
```

`--dir` accepts only a `memory_dir` that `native-memory` reported; any other path is refused. The transcript listing carries no message text; one conversation's turns come back only through `transcript`, secret-scrubbed, cut per turn, and paged with `--limit` / `--offset`. The header says how many turns the file holds in total, so a short page is never mistaken for a short conversation.

## Which models an agent offers

The model pickers ask the installed agent what it can run on, over the daemon's API:

```bash
curl -s -H "X-Coffer-Token: $COFFER_TOKEN" \
  http://127.0.0.1:8000/api/v1/agent-providers/claude_code/models
```

Each entry has an `id` (passed to the agent verbatim), a label, the reasoning-effort levels it supports, and a default effort — `null` when the agent publishes none. Coffer stores no model list, so a model released after your Coffer build appears without an upgrade. If one source is unavailable — the agent's CLI is not installed or not signed in — only that source's entries go missing and the request still succeeds. With a [connection](/guide/providers) active for the agent, the connection's curated models are listed instead.

## Web UI walkthrough

The **Agents** page in the [Web UI](/guide/web-ui) covers the same flow without the terminal:

1. Open **Agents** and click **Detect** to scan for installed agents. The detect dialog lists what was found; confirm an agent to register it.
2. The agent detail page has seven tabs — **Overview**, **Skills**, **MCP servers**, **Plugins**, **Memory**, **Conversations**, and **Config files**.
3. On the **Config files** tab, open any curated config file and edit it in place. Saving validates the file's format first — malformed JSON or TOML is rejected and the file on disk is left untouched — then writes atomically, keeping the previous contents next to the file as `.bak`. If the file changed on disk while you were editing, the save is refused rather than applied over the top, and you are offered a reload.
4. Use the **Install Coffer MCP** toggle in the header to add or remove the `coffer` entry, with a live status indicator.
5. On the **Skills** tab, toggle each skill on or off for this agent, or use **Install skills** to bind more. The **MCP servers** tab shows the gateway install status alongside the agent's own direct MCP entries, each with **Adopt** (bring it into Coffer as a managed resource) and **Delete** (remove it from the agent's file, keeping a `.bak`).
6. **Plugins** lists the agent's own plugins with an enable/disable switch and an uninstall. **Memory** shows what this agent reaches through Coffer, its session-start **Delivery** state, and a read-only view of the agent's *own* native memory stores. **Conversations** reads the agent's own transcripts.

See the [Web UI guide](/guide/web-ui#agents) for what each tab holds in detail.

## Troubleshooting

- **Detection missed an installed agent** — its config directory is not at the standard location. Register it with `coffer agent add <type> --config-dir <path>`.
- **"not writable" / "directory missing" on add** — fix the directory's permissions, create it, or pass a different `--config-dir`.
- **Registered an agent you don't want** — `coffer agent rm <name>`. It keeps appearing as a detection candidate while installed, but stays out of the registry until you confirm it again.

[Model providers →](/guide/providers)
