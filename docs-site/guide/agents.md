# Agents

An **agent** is a registered local AI coding agent that Coffer can manage — its config files and its connection to Coffer's own MCP server. Two agent types ship today: `claude_code` and `codex`.

Coffer never registers an agent automatically. It can **detect** the agents installed on your machine, but you confirm each one before it is registered.

## Detect & register

Run detection to discover installed agents, then register the ones you want:

```bash
coffer agent detect            # → claude_code (detected), codex (detected)
coffer agent add claude_code   # register; --name defaults to claude-code
coffer agent add codex --name my-codex --description "work laptop"

coffer agent list              # → claude-code | claude_code | registered
```

- `coffer agent detect` scans for installed agents and reports what it finds. Nothing is registered by this step — it is discovery only.
- `coffer agent add <type>` registers an agent. `<type>` is `claude_code` or `codex`. `--name` is optional and defaults to a per-type name (for example, `claude_code` → `claude-code`). Optional flags: `--skill-dir PATH` and `--description TEXT`.
- `coffer agent list` shows all registered agents with their type and status.
- `coffer agent show <name>` prints a registered agent's details; `coffer agent rm <name>` removes it.

## Edit config files

Each agent exposes a curated set of config files, addressed by a short **key**:

| Type          | Key              | File                                                 |
| ------------- | ---------------- | ---------------------------------------------------- |
| `claude_code` | `settings`       | `~/.claude/settings.json`                            |
| `claude_code` | `settings_local` | `~/.claude/settings.local.json`                      |
| `claude_code` | `global`         | `~/.claude.json` (also holds user-scope MCP servers) |
| `claude_code` | `memory`         | `~/.claude/CLAUDE.md`                                |
| `codex`       | `config`         | `~/.codex/config.toml`                               |
| `codex`       | `memory`         | `~/.codex/AGENTS.md`                                 |

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

## Install Coffer's MCP server

A single command writes (or removes) Coffer's own MCP server entry — a `coffer` stdio entry pointing at the `coffer-mcp-shim` binary — into an agent's config:

```bash
coffer agent mcp status claude-code      # → not installed / installed
coffer agent mcp install claude-code     # write the coffer entry
coffer agent mcp uninstall claude-code   # remove it
```

Install is idempotent: running it again updates the existing entry in place rather than duplicating it. Once installed, the agent reaches every server you have registered with Coffer through the shim — see [Connect a client](/guide/connect-client).

## Web UI walkthrough

The **Agents** page in the [Web UI](/guide/web-ui) covers the same flow without the terminal:

1. Open **Agents** and click **Detect** to scan for installed agents. The detect dialog lists what was found; confirm an agent to register it.
2. On an agent's detail page, open any curated config file in the editor. The editor validates format on save, writes atomically with a `.bak` backup, and includes a **find/replace** box that scrolls to the match.
3. Use the **Install Coffer MCP** toggle to add or remove the `coffer` entry, with a live status indicator.
4. Set the agent's skill directory with the folder picker.

[Connect a client →](/guide/connect-client)
