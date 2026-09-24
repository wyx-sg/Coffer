---
title: Agents
description: Register Claude Code and Codex with Coffer, install Coffer's MCP entry into them, and manage their config files, MCP entries, plugins, models, memory and transcripts.
---

# Agents

An agent is a coding agent installed on your machine that Coffer delivers to: Claude Code or Codex. This page covers registering agents, installing Coffer's MCP entry into them, and everything Coffer lets you see and change in an agent's own files.

## What agents are for

Everything Coffer shares — MCP servers, skills, knowledge, memory, model providers — ends up in an agent. Registering an agent tells Coffer where that agent keeps its configuration, so Coffer can:

- write a `coffer` MCP entry into it, so the agent reaches every upstream MCP server through [one gateway](/guides/mcp-servers);
- link [skills](/guides/skills) into its `skills/` folder;
- project a [model provider](/guides/providers) into its native config;
- show you its config files, MCP entries, plugins, native memory and conversation transcripts in one place.

Coffer supports two agent types:

| Type | Product | Default config directory | Discovered by |
| --- | --- | --- | --- |
| `claude_code` | Claude Code (CLI and IDE/desktop forms) | `~/.claude` | the directory existing |
| `codex` | OpenAI Codex (CLI and IDE forms) | `~/.codex` | the directory existing |

The CLI and IDE forms of each product read the same config directory, so one registered agent covers both. The Claude Desktop chat app has its own configuration and is not a supported agent.

::: info The agent's files are the source of truth
Coffer never copies an agent's configuration into its database. Config files, MCP entries, plugins, native memory and transcripts are read from disk every time you look at them. The agent record itself holds only the type, the config directory, an optional description and the model binding.
:::

## Register an agent

### From detected agents

Coffer scans for each supported type's config directory and offers what it finds. It never registers anything on its own, and the daemon does not auto-register agents at startup.

**Web UI:** open **Agents** and click **Add agent**. The dialog lists **Detected agents**; tick the ones you want and click **Add selected**.

**CLI:**

```sh
coffer agent detect
# detected: codex -> add with `coffer agent add codex --name codex`

coffer agent add codex
# registered: agent codex
```

`--name` is optional. Without it, the name defaults to the type with underscores turned into hyphens: `claude-code`, `codex`.

### Manually, with a custom config directory

Register manually when an agent runs against a non-default directory — Claude Code through `CLAUDE_CONFIG_DIR`, Codex through `CODEX_HOME`.

**Web UI:** in the **Add agent** dialog, click **Add manually**, choose the type, and pick the **Config directory (optional)** with the folder picker.

**CLI:**

```sh
coffer agent add claude_code --name claude-work --config-dir ~/work/.claude
```

Before accepting the directory, Coffer creates `<config_dir>/skills`, then checks that the directory exists, is a directory, is writable, and is not a system location (`/etc`, `/usr`, `/var` outside `/var/folders/`, `/System`, `C:\Windows`, `C:\Program Files` and similar). A rejected registration leaves nothing behind.

Only one agent may be registered per config directory, and names are unique. Two agents of the same type on different directories are allowed.

When Coffer itself starts an agent for such a registration — a [chat](/guides/chat) or [channel](/guides/channels) turn, a model-list probe, a plugin uninstall — it sets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` to that directory, so the agent reads the skills, MCP entry and settings Coffer put there.

### Edit, rename, disable and remove

```sh
coffer agent edit claude-work --config-dir ~/work2/.claude --description "Work account"
coffer resource rename agent claude-work claude-office
coffer resource disable agent claude-office
coffer agent rm claude-office
```

In the web UI, the agent's detail page has **Edit** (config directory and description) and **Delete** in its header.

- **Rename** changes only the label. Everything that refers to an agent — reach lists, a channel's default agent, the installed MCP entry — holds the agent's immutable `uid`, so a rename breaks nothing.
- **Disable** makes Coffer stop writing into and reading from the agent: its delivered skills are removed, its native memory is not aggregated, and its config no longer feeds the model catalogue. Enabling it again restores what the skills grant. This switch is on the CLI and REST API only.
- **Remove** deletes the registration and removes the skills Coffer delivered. The agent stays installed, and `coffer agent detect` offers it again for as long as its config directory exists.

::: warning Removing an agent leaves its MCP entry in place
Removing an agent does not uninstall the `coffer` MCP entry from its config. That entry keeps reporting a `uid` no registered agent has, so its sessions see only servers that reach every agent. Run `coffer agent mcp uninstall <name>` before removing, or re-install after registering the agent again.
:::

## Install Coffer's MCP entry

One action writes a `coffer` stdio MCP server entry into the agent's own config, pointing at `coffer-mcp-shim`. After that, the agent reaches every enabled upstream server, Coffer's own tools, and its delivered knowledge through a single connection.

**Web UI:** on the agent's detail page, click **Install Coffer MCP**. On the **Agents** list you can select several agents and use the bulk **Install Coffer MCP** action. The **Coffer MCP** status reads **Installed** or **Not installed**.

**CLI:**

```sh
coffer agent mcp install claude-code
# installed Coffer MCP into agent claude-code (/Users/you/.coffer/bin/coffer-mcp-shim)

coffer agent mcp status claude-code
# installed: True
# command: /Users/you/.coffer/bin/coffer-mcp-shim

coffer agent mcp uninstall claude-code
```

Restart the agent (or reload its MCP servers) after installing so it starts the shim.

### What gets written where

| Agent | File | Entry |
| --- | --- | --- |
| Claude Code, default directory | `~/.claude.json` | `mcpServers.coffer` |
| Claude Code, custom directory | `<config_dir>/.claude.json` | `mcpServers.coffer` |
| Codex | `<config_dir>/config.toml` | `[mcp_servers.coffer]` |

For Claude Code the entry looks like this:

```json
{
  "mcpServers": {
    "coffer": {
      "command": "/Users/you/.coffer/bin/coffer-mcp-shim",
      "args": ["--agent-uid", "9a006a32d0bf5787955c43d54e4b44e9"]
    }
  }
}
```

For Codex:

```toml
[mcp_servers.coffer]
command = "/Users/you/.coffer/bin/coffer-mcp-shim"
args = ["--agent-uid", "9a006a32d0bf5787955c43d54e4b44e9"]
```

Install is idempotent: installing again rewrites the `coffer` entry in place and never adds a second one. Uninstalling when nothing is installed succeeds and changes nothing. Both are backed up and audited (`agent_mcp_installed`, `agent_mcp_uninstalled`). The install status is read from the file each time; Coffer does not store it.

### Why the shim path is absolute

The daemon may run from the desktop app, a login service or a virtualenv, none of which inherit your shell's `PATH`, and the agent may not either. Coffer therefore writes the full path. It resolves the shim in this order:

1. `COFFER_MCP_SHIM_PATH`, if set and the file exists;
2. `coffer-mcp-shim` on the daemon's `PATH`;
3. the scripts directory of the Python interpreter running the daemon (where `pip` and `uv` put console scripts);
4. the binary bundled beside the running executable.

When the answer is the installed build, Coffer writes the stable `~/.coffer/bin/coffer-mcp-shim` link rather than a versioned directory, so the entry survives upgrades. If no shim can be found, install fails with an error naming the missing binary and writes nothing.

### The agent uid and reach

The `--agent-uid` argument is how the gateway knows which agent a session belongs to. The shim passes it in the MCP `initialize` handshake, and the gateway uses it for the whole session to decide which servers the agent may see. A server whose [reach](/architecture/resource-framework) names only certain agents is hidden from every other session.

The entry carries the uid rather than the name because Coffer writes it once into a file it does not otherwise revisit; a name would go stale on the first rename. A hand-written shim entry without `--agent-uid` still works, but its session is unidentified and sees only servers that reach every agent. See [Connect a client](/guides/connect-a-client) for the details.

## What Coffer reads and what it writes

Coffer touches an agent's files through a short list of documented surfaces:

| Surface | Coffer reads | Coffer writes |
| --- | --- | --- |
| Allowlisted config files | yes | yes, when you save in the editor or CLI |
| MCP entries in the agent's config | yes | install/uninstall of `coffer`, remove, adopt |
| Plugins | inventory and enabled state | the enabled switch; uninstall by the type's own strategy |
| Model provider keys | yes (boot self-check) | only when you switch a [provider](/guides/providers) |
| Native memory stores | yes | never |
| Transcripts | yes | never |
| Codex `auth.json` | never | never |

Every write:

- addresses a file by its allowlist **key**, never by a path you supply — an unknown key is a 404 with no file access;
- validates `json` and `toml` content before writing and refuses malformed input with the file untouched;
- replaces the file atomically (temp file plus rename);
- keeps the previous content as `<file>.bak`, rotating older copies to `.bak.1` and `.bak.2`;
- edits Codex's `config.toml` with `tomlkit`, so your comments, key order and Codex's own internal tables (`[marketplaces.*]`, `[hooks.state.*]`, `[projects.*]`) survive byte-for-byte;
- records an audit entry.

When a config file cannot be parsed, the MCP and Plugins tabs show the parse error and switch to read-only for that file; the rest of the agent page keeps working.

## Edit config files

Each type has a fixed allowlist:

| Type | Key | File |
| --- | --- | --- |
| `claude_code` | `settings` | `<config_dir>/settings.json` |
| | `settings_local` | `<config_dir>/settings.local.json` |
| | `global` | `~/.claude.json` (default dir) or `<config_dir>/.claude.json` (custom dir) |
| | `instructions` | `<config_dir>/CLAUDE.md` |
| | `subagents` | `<config_dir>/agents/` — a directory, one Markdown file per subagent |
| `codex` | `config` | `<config_dir>/config.toml` |
| | `instructions` | `<config_dir>/AGENTS.md` |
| | `hooks` | `<config_dir>/hooks.json` |

**Web UI:** open the agent and choose **Config files**. Select a file to view it; the viewer becomes editable behind **Edit**. Beside the content you can open the file in your external editor or reveal it in the file manager. An unsaved draft asks before you switch files, tabs or pages.

**CLI:**

```sh
coffer agent config ls claude-code
coffer agent config cat claude-code settings
coffer agent config edit claude-code instructions          # opens $EDITOR
coffer agent config edit codex config --from-file ./config.toml

# Directory entries (Claude Code subagents)
coffer agent config files claude-code subagents
coffer agent config write claude-code subagents reviewer.md --from-file ./reviewer.md
coffer agent config rm claude-code subagents reviewer.md
```

Reading a file that does not exist returns empty content and does not create it. Files inside a directory entry must stay inside it and end in `.md`.

::: tip Concurrent edits are refused, not overwritten
Every read returns a fingerprint of the content. The editor and `coffer agent config edit` send it back with the save, and if the file changed on disk in the meantime — the agent itself rewrote it, or you saved it elsewhere — the write is refused with `CONFIG_FILE_STALE` (exit code 5 on the CLI) and the file is left as it is. Re-open and save again.
:::

If a `CLAUDE.md` or `AGENTS.md` contains a Coffer-written memory block, the editor marks it as a leftover that is safe to delete. Coffer delivers memory through a hook, not through these files (see [Memory](/guides/memory#how-agents-receive-memory)).

## Manage the agent's own MCP entries

Agents often carry MCP servers configured directly in their own files. The **MCP servers** tab shows both groups: **Via Coffer gateway** (what Coffer serves) and **Direct servers** (entries in the agent's files, labelled with the file they came from).

| Type | Direct entries are read from |
| --- | --- |
| Claude Code | `mcpServers` in `.claude.json` (the `global` file) and in `settings.json` |
| Codex | `[mcp_servers.*]` in `config.toml` (the `enabled` flag is shown but never written) |

You can do two things with a direct entry:

- **Remove** it from its source file (atomic write, `.bak` kept, audited as `agent_mcp_entry_removed`).
- **Adopt into Coffer**: Coffer registers the entry as an `mcp_server` resource, checks that it reads back, and only then removes the direct entry. Any failure rolls the new resource back and leaves the agent's file byte-identical. The server is then served to every agent through the gateway.

```sh
coffer agent mcp entries claude-code
coffer agent mcp remove-entry claude-code old-server --source settings
coffer agent mcp adopt claude-code github --secret GITHUB_TOKEN=github/token
```

When the entry's environment or headers carry a non-empty value under a secret-looking key (containing `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `APIKEY`, `CREDENTIAL` or `AUTHORIZATION`), adoption requires a `--secret KEY=REF` mapping for each one. Coffer stores the current value in its [encrypted credential store](/guides/credentials) under the ref you name, and the new resource config carries only the ref. A name collision is refused with a suggested alternative (`--name` to pick one). For a Claude Code name that appears in both files, pass `--source` with the file's key (`global` or `settings`). The `coffer` entry itself is never removable or adoptable this way.

## Plugins

The **Plugins** tab lists installed plugins as `<name>@<marketplace>`, with their enabled state, marketplace, version, author, and the skills, commands and MCP servers each plugin bundles. A plugin whose cache directory is gone is marked **Cache missing**; Coffer does not try to repair it.

```sh
coffer agent plugin list claude-code
coffer agent plugin disable claude-code formatter@acme
coffer agent plugin enable claude-code formatter@acme
coffer agent plugin uninstall codex formatter@acme
```

| | Claude Code | Codex |
| --- | --- | --- |
| Inventory read from | `plugins/installed_plugins.json`, `known_marketplaces.json` | `[plugins."…"]` and `[marketplaces.*]` in `config.toml` |
| Enable/disable writes | `enabledPlugins` in `settings.json` only | the plugin's own `enabled` field only |
| Uninstall | runs `claude plugin uninstall <id>` | removes the entry from `config.toml` and deletes `plugins/cache/<marketplace>/<plugin>/` |

Claude Code's own inventory files are never written by Coffer. When the `claude` CLI is not on `PATH`, uninstall is unavailable (`PLUGIN_UNINSTALL_UNSUPPORTED`) and the web UI hides the action. Installing plugins and managing marketplaces stay with the agent's own tooling.

## Models

The model catalogue answers "which models can this agent be put on". Coffer reads it back from the installed agent every time, so a newly released model appears without a Coffer release:

- **Claude Code:** the model aliases embedded in the `claude` binary (for example `opus`, `sonnet`, `haiku`), plus `additionalModelOptionsCache` from `.claude.json`. Reasoning-effort levels come from the installed Claude Agent SDK; no default level is reported, because the runtime does not publish one.
- **Codex:** the `model/list` RPC of Codex's app server (run with `CODEX_HOME` set to the agent's directory), plus the models named in `config.toml`. Each model carries its own effort levels and default.

Each source fails on its own: an unauthenticated Codex or a changed binary layout costs only that source's models.

```sh
coffer agent models claude_code
# opus  Opus 5.5  efforts: low, medium, high, xhigh, max
# sonnet  Sonnet 5  efforts: low, medium, high, xhigh, max
```

`coffer agent models` takes the agent **type**, not a name. When two agents of one type are registered, the first enabled one in name order answers. When an active [model provider](/guides/providers) curates a model list for the agent, pickers offer that list instead.

The agent record carries the model binding that provider projection writes into the agent's config:

```sh
coffer agent edit claude-code --model sonnet --fast-model haiku
coffer agent edit claude-code --clear-fast-model
coffer agent edit codex --model gpt-5.5 --wire-api responses
```

For Codex, `responses` is the only accepted `--wire-api` value; Codex refuses to load a `config.toml` with any other. A change takes effect on disk the next time the agent's provider is switched.

## Native memory and conversations

The **Memory** tab lists the agent's own memory stores, read-only:

- **Claude Code:** one store per project at `<config_dir>/projects/<slug>/memory/`, labelled with the real project directory.
- **Codex:** the global `<config_dir>/memories/MEMORY.md`, split into one row per project it routes task groups to.

Opening a row shows the store's files with a read-only preview. The same tab carries the memory-delivery hook install, which is covered in [Memory](/guides/memory).

The **Conversations** tab lists the agent's local transcripts (`<config_dir>/projects/**/*.jsonl` for Claude Code, `<config_dir>/sessions/**/*.jsonl` for Codex) with title, project, message count and activity times, searchable and sortable. Opening one renders the session as a conversation with a **Contents** list of your prompts; the harness's own injected blocks are folded under **Harness context**.

```sh
coffer agent native-memory claude-code
coffer agent native-memory-files claude-code --dir <memory_dir>
coffer agent transcripts claude-code -q "release" --sort message_count
coffer agent transcript claude-code --path <source_path> --limit 50
```

Transcript text is secret-scrubbed before it is shown, long turns are cut and flagged, and a session is read in windows of turns. Coffer never writes, stores or sends transcripts or native memory anywhere.

## Skills on an agent

The **Skills** tab shows the skills Coffer delivers to the agent (**Managed by Coffer**) and any **Unmanaged skills** sitting in the agent's skill folders, which you can adopt into Coffer's library. Which skills reach the agent is decided per skill; see [Skills](/guides/skills).

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| **Install Coffer MCP** fails naming `coffer-mcp-shim` | The daemon cannot find the shim | Set `COFFER_MCP_SHIM_PATH` in the daemon's environment, or reinstall Coffer so `~/.coffer/bin/coffer-mcp-shim` exists. |
| Status says **Installed** but the agent has no Coffer tools | The agent was not restarted, or reads a different config directory | Restart the agent. For a custom directory, start the agent with `CLAUDE_CONFIG_DIR` / `CODEX_HOME` pointing at it. |
| **Availability** shows **Not found** | The agent's CLI (`claude` or `codex`) is not on the daemon's `PATH` | Install the CLI, or make it visible to the daemon. |
| A save fails with `CONFIG_FILE_STALE` | The file changed after you opened it | Re-open the file and save again. |
| Plugin uninstall is missing | `claude` is not on `PATH` | Run `claude plugin uninstall <id>` yourself. |

## Related

- [Connect a client](/guides/connect-a-client) — the shim, the HTTP endpoint and agent identity
- [MCP servers](/guides/mcp-servers) — what the gateway serves to agents
- [Model providers](/guides/providers) — projecting an endpoint into an agent
- [Resource framework](/architecture/resource-framework) — reach and immutable uids
- Spec: [agent-registry](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/spec.md), [claude-code](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/claude-code/spec.md), [codex](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/codex/spec.md)
