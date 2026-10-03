---
title: Agents
description: Register Claude Code and Codex with Coffer, connect them to Coffer, and manage their config files, MCP entries, plugins, hooks, models, memory and transcripts.
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

| Type | Product | Default config directory | Program Coffer looks for |
| --- | --- | --- | --- |
| `claude_code` | Claude Code (CLI and IDE/desktop forms) | `~/.claude` | `claude` |
| `codex` | OpenAI Codex (CLI and IDE forms) | `~/.codex` | `codex` |

The CLI and IDE forms of each product read the same config directory, so one registered agent covers both. The Claude Desktop chat app has its own configuration and is not a supported agent.

### One agent per type

A machine has at most one registered agent of each type, and the agent's name **is** its type: `claude-code` or `codex`. You do not choose a name, and an agent has no title or description. Everywhere Coffer asks which agent you mean — `coffer agent …`, `coffer path agent`, `coffer scan --agent`, the `--agents` scope of a skill or MCP server, and every `/api/v1/agents/{uid}/…` route — you can give the type (`claude-code`; `claude_code` also reads) or the agent's uid.

Besides its type, the only setting an agent has is its **config directory**, plus the [model binding](#models). Registering uses the type's standard directory (`~/.claude`, `~/.codex`) unless you say otherwise. Pointing Coffer at a different directory moves the one agent there; it never adds a second one. Registering a type that is already registered is refused with `409 AGENT_TYPE_REGISTERED`.

::: details Upgrading from a build that allowed several agents of one type
Earlier builds let you register several agents of one type under names you chose. On upgrade, a database migration keeps one agent per type and drops the rest. It keeps, in this order of preference, the agent that is connected to Coffer (its Coffer MCP entry carries its uid), then an enabled one, then the most recently used, then the one on the standard directory. Every reach list and every channel's default agent that named a dropped agent is re-pointed at the kept one, the kept agent is renamed to its type, and each dropped agent is logged in the daemon log as `migration.0109.agent_dropped`. A dropped agent's config directory keeps whatever Coffer had written there, such as skill links or its `coffer` MCP entry; remove those by hand if you no longer use that directory. Titles and descriptions on agents are cleared.
:::

::: info The agent's files are the source of truth
Coffer never copies an agent's configuration into its own store. Config files, MCP entries, plugins, native memory and transcripts are read from disk every time you look at them. The agent record itself holds only the type, the config directory and the model binding.
:::

## Register an agent

### From detected agents

Coffer detects an agent from two signals: its program on your `PATH` — the `PATH` your login shell gives you, so an agent installed with Homebrew or a Node version manager is found even when the daemon was started from the Dock — and its config directory. It reads the program's version (`claude --version`, `codex --version`) along the way. It never registers anything on its own, and the daemon does not auto-register agents at startup.

Coffer reports every supported type, registered or not, in one of these states:

| State | Program | Config directory | What you can do |
| --- | --- | --- | --- |
| **Installed** | found | present | Add it. |
| **Installed, never run** | found | not yet created | Add it. Registering it at its standard directory creates that directory, holding only what Coffer needs there (its `skills` folder). |
| **Not installed** | missing | present | Nothing to add: the directory is left from an earlier install. Reinstall the agent, or ignore it. |
| **Missing** | missing | absent | Nothing on this machine. The type is still listed, so every type always has a row. |

For each type Coffer looks at its standard directory and, when the daemon's environment sets the type's own variable (`CLAUDE_CONFIG_DIR` for Claude Code, `CODEX_HOME` for Codex), at the directory that names. That second directory is never a second agent: when the standard one exists it is offered as **use a different config directory** for the one agent, and when only the named one exists it is the directory Add registers. Coffer does not search the rest of your disk; to use any other directory, see [Use a different config directory](#use-a-different-config-directory). A type already registered is not offered again.

**Web UI:** the **Agents** page always has exactly two rows, Claude Code then Codex, whether or not each is installed or added. Detection is automatic — when the page opens, when the window regains focus, and every few minutes — so there is no Detect button and no Add-agent dialog. Each row reads one state and offers the one action it calls for:

| Row reads | Meaning | Action |
| --- | --- | --- |
| **Detected, not added** | installed, config directory present | **Add** |
| **Installed, never run** | installed, directory not created yet (marked *not created*) | **Add** — the preview names the directory it creates |
| **Config left behind** | a directory with no program on `PATH` | **Copy prompt** (the reinstall hand-off); a notice under the row offers the same prompt and **Reveal folder** |
| **Not installed** | neither | **Copy prompt** (the install hand-off) |
| **Connected** / **Not connected** / **Needs repair** | added; its Coffer connection is complete, absent or partial | **Disconnect** / **Connect** / **Repair** |
| **Disabled** | added and switched off | **Enable** |

Coffer does not install agents, and installing one depends on the machine, so a row whose program is not found hands the job to an agent instead of naming an install command. **Copy prompt** copies a prompt the daemon writes: install (or reinstall) this agent on this machine, keep its existing config directory, make sure its program is found on the `PATH` Coffer looks on (the prompt lists it) and confirm with `claude --version` or `codex --version`, then come back and choose **Check again** — leaving the login to you. Paste it into any assistant. While another managed agent is available, the row's ⋯ menu also offers **Ask an agent**, which opens a new conversation with the prompt in the composer, unsent. The agent's page offers the same prompt on its empty state and on its Overview tab's problem states. You can still install the agent yourself the way its maker documents; the row updates on its own once the program is on your `PATH`.

**Add** registers the agent at its standard directory and connects it. It first opens a preview — every file it will write and the entries it adds — and writes nothing until you apply it. On a first run with both agents installed and neither added, **Add both** previews and adds the two in one confirmation. A registered row also shows its model and how many skills, MCP servers and plugins reach it, and opens the agent's page.

**CLI:**

```sh
coffer scan
# lists the types seen here that are not registered (kind "agent"), one row per type,
# with its state and version and — when it can be added — the command that registers it

coffer agent add codex            # register the codex agent at ~/.codex
# registered: agent codex
```

The command `coffer scan` prints is `coffer agent add <type>`, with `--config-dir` added only when the directory it found is not the type's standard one.

`coffer agent prompt <type>` prints the same install or reinstall prompt the Agents page copies, while that type's program is not found (`--json` returns it under `handoff`); when the program is found it says there is nothing to hand off and exits with code 5. `coffer agent show <name>` points at it for a registered agent whose program is gone.

### Use a different config directory

Claude Code reads another directory when started with `CLAUDE_CONFIG_DIR`, Codex when started with `CODEX_HOME`. If that is how you run an agent, tell Coffer the directory. At registration:

```sh
coffer agent add claude-code --config-dir ~/work/.claude
```

For an agent that is already registered, move it:

```sh
coffer agent edit claude-code --config-dir ~/work/.claude
```

**Web UI:** choose **Use a different config directory…** from the row's **⋯** menu (or the agent page's). Pick the folder with the native folder dialog (an in-app browser only where the host has none); the dialog lists which of the type's usual files are there. For an agent that is not added yet, this registers it at that directory.

Before accepting the directory, Coffer creates `<config_dir>/skills`, then checks that the directory exists, is a directory, is writable, and is not a system location (`/etc`, `/usr`, `/var` outside `/var/folders/`, `/System`, `C:\Windows`, `C:\Program Files` and similar). A rejected registration leaves nothing behind. A directory other than the standard one must already exist; only the standard directory of an installed, never-run agent is created for you. Moving an agent re-delivers its skills to the new directory.

When Coffer itself starts an agent registered on a directory other than the standard one — a [chat](/guides/chat) or [channel](/guides/channels) turn, a model-list probe, a plugin uninstall — it sets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` to that directory, so the agent reads the skills, MCP entry and settings Coffer put there.

### Edit, disable and remove

```sh
coffer agent edit claude-code --config-dir ~/work2/.claude
coffer agent disable claude-code
coffer agent rm claude-code
```

In the web UI, the **⋯** menu on an agent's row and on its page carries **Use a different config directory…**, **Reveal config directory**, **Copy uid**, **Disconnect**, **Disable** / **Enable** and **Remove from Coffer**.

- **Edit** changes the config directory or the [model binding](#models). The name is the type and cannot change. Everything that refers to an agent — reach lists, a channel's default agent, the installed MCP entry — holds the agent's immutable `uid`.
- **Disable** makes Coffer stop writing into and reading from the agent: its delivered skills are removed, its native memory is not aggregated, and its config no longer feeds the model catalogue. Enabling it again restores what the skills grant. In the web UI it is **Disable** in the ⋯ menu; a disabled agent's page offers **Enable**.
- **Remove** deletes the registration and removes the skills Coffer delivered. The agent stays installed, and `coffer scan` offers it again for as long as its program or its config directory is there.

::: warning Removing an agent leaves Coffer's entries in place
On the command line and REST API, removing an agent does not disconnect it. The `coffer` MCP entry keeps reporting a `uid` no registered agent has, so its sessions see only servers that reach every agent. Run `coffer agent disconnect <type>` before removing, or connect again after registering the agent again. **Remove from Coffer** in the web UI disconnects first, then removes.
:::

## Connect an agent to Coffer

Connecting writes everything Coffer needs into the agent's own config, in one action:

| Part | What it does | When |
| --- | --- | --- |
| Gateway MCP entry | A `coffer` stdio MCP server entry pointing at `coffer-mcp-shim`. The agent reaches every enabled upstream server, Coffer's own tools, and its delivered knowledge through it. | Always |
| Memory delivery hook | Four hook entries — session start, each prompt, and before and after each shell command — through which Coffer hands the agent its memory. See [Memory](/guides/memory#install-the-hook). | Always |

Disconnecting removes both, and only Coffer's own entries; everything else in those files stays as it was.

**Web UI:** the agent page's header offers **Connect to Coffer** when the agent is not connected or its connection is partial (reads **Needs repair**); the Overview tab's **Connection** card shows each part — the MCP entry and the memory hook, with the file each lives in and whether it is current. On the **Agents** list the **Coffer** column reads **Connected**, **Not connected** or **Needs repair**, with **Connect** or **Repair** on the row. Every connect, repair and disconnect opens the same **Review changes** preview first: a repair lists only the missing parts, a disconnect only the lines it removes. If a write fails partway, the preview says which change failed, keeps the ones that applied, and offers to retry only the failed one.

**CLI:**

```sh
coffer agent connect claude-code
# connected agent claude-code to Coffer
#   gateway MCP entry: installed (/Users/you/.coffer/bin/coffer-mcp-shim)
#   memory delivery hook: installed (: coffer-memory; coffer memory hook --agent-uid …)

coffer agent show claude-code                # the connection, beside the agent's record (--json for the raw answer)
# ...
# coffer_connection: connected
#   gateway MCP entry: installed (/Users/you/.coffer/bin/coffer-mcp-shim)

coffer agent disconnect claude-code
```

Restart the agent (or reload its MCP servers) after connecting so it starts the shim.

An agent that carries the gateway entry but not the hook reads **Needs repair** until you connect it again.

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

The memory hook's four entries are described in [Filesystem](/reference/filesystem).

Connecting is idempotent: connecting again rewrites each entry in place and never adds a second one. Disconnecting when nothing is installed succeeds and changes nothing. Every write is backed up and audited by part (`agent_mcp_installed` / `agent_mcp_uninstalled`, `memory_delivery_installed` / `memory_delivery_removed`). The connection status is read from the files each time; Coffer does not store it.

### Why the shim path is absolute

The daemon may run from the desktop app, a login service or a virtualenv, none of which inherit your shell's `PATH`, and the agent may not either. Coffer therefore writes the full path. It resolves the shim in this order:

1. `COFFER_MCP_SHIM_PATH`, if set and the file exists;
2. `coffer-mcp-shim` on the daemon's `PATH`;
3. the scripts directory of the Python interpreter running the daemon (where `pip` and `uv` put console scripts);
4. the binary bundled beside the running executable.

When the answer is the installed build, Coffer writes the stable `~/.coffer/bin/coffer-mcp-shim` link rather than a versioned directory, so the entry survives upgrades. If no shim can be found, install fails with `SHIM_NOT_FOUND`, naming the missing binary, and writes nothing. The refusal carries a hand-off prompt that lists every place Coffer looked and asks an agent to find or reinstall the shim so it resolves at `~/.coffer/bin/coffer-mcp-shim`: the Connect review offers it as **Copy prompt** beside **Retry**, and `coffer agent connect` prints it under the error.

### The agent uid and reach

The `--agent-uid` argument is how the gateway knows which agent a session belongs to. The shim passes it in the MCP `initialize` handshake, and the gateway uses it for the whole session to decide which servers the agent may see. A server whose [reach](/architecture/resource-framework) names only certain agents is hidden from every other session.

The entry carries the uid because Coffer writes it once into a file it does not otherwise revisit, and the uid is the identity every other record holds. A hand-written shim entry without `--agent-uid` still works, but its session is unidentified and sees only servers that reach every agent. See [Connect a client](/guides/connect-a-client) for the details.

## What Coffer reads and what it writes

Coffer touches an agent's files through a short list of documented surfaces:

| Surface | Coffer reads | Coffer writes |
| --- | --- | --- |
| Allowlisted config files | yes | yes, when you save in the editor or CLI |
| MCP entries in the agent's config | yes | install/uninstall of `coffer`, remove, adopt |
| Plugins | inventory and enabled state | the enabled switch; uninstall by the type's own strategy |
| Model provider keys | yes (checked on every reconcile pass) | when you switch a [provider](/guides/providers), and to bring a projection whose values went stale back in line |
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

**Web UI:** open the agent and choose **Config files**. Select a file to view it; the viewer becomes editable behind **Edit**. Beside the content you can open the file in your external editor or reveal it in the file manager. An unsaved draft asks before you switch files, tabs or pages, in the same **Leave without saving?** dialog every editor uses.

**CLI:**

```sh
coffer path agent claude-code config                        # where each allowlisted file is
coffer agent config edit claude-code instructions          # opens $EDITOR
coffer agent config edit codex config --from-file ./config.toml

# Directory entries (Claude Code subagents)
coffer agent config edit claude-code subagents/reviewer.md --from-file ./reviewer.md
coffer agent config rm claude-code subagents/reviewer.md
```

To read a file, open the path `coffer path agent <type> config` prints with your own tools. Reading a file that does not exist returns empty content and does not create it. Files inside a directory entry must stay inside it and end in `.md`.

::: tip Concurrent edits are refused, not overwritten
Every read returns a fingerprint of the content. The editor and `coffer agent config edit` send it back with the save, and if the file changed on disk in the meantime — the agent itself rewrote it, or you saved it elsewhere — the write is refused with `CONFIG_FILE_STALE` (exit code 5 on the CLI) and the file is left as it is. Re-open and save again.
:::

## Manage the agent's own MCP entries

Agents often carry MCP servers configured directly in their own files. The **MCP servers** tab lists both in one table: Coffer's servers (served through the gateway entry) and the agent's own entries, each row marked with its owner and the file it lives in. The owner filter — **All**, **Coffer’s**, **The agent’s own** — narrows it and is kept in the address (`?owner=`). An own entry offers **Adopt**; one that duplicates a registered MCP server offers **Remove duplicate**, which takes it out of the agent's file because the gateway already serves it.

| Type | Direct entries are read from |
| --- | --- |
| Claude Code | `mcpServers` in `.claude.json` (the `global` file) and in `settings.json` |
| Codex | `[mcp_servers.*]` in `config.toml` (the `enabled` flag is shown but never written) |

Click a direct server's name to open its detail page. It shows, read-only, everything the agent's file holds for that server: the transport, the command and each argument (or the URL), the working directory, the `enabled` flag where the format has one, the names of its environment variables and HTTP headers, any other keys the entry carries, and the config file it lives in, with **Open in editor** and **Reveal** beside the path. Secret values never leave the daemon: environment and header values are shown only as *set* or *secret · hidden*, and any other key whose name looks secret (the pattern below) shows as *hidden*. Coffer does not start a direct server to show this page, so it lists no tools. The page carries the same two actions as the row; use the title bar's back arrow to return to the agent's **MCP servers** tab.

You can do two things with a direct entry:

- **Remove** it from its source file (atomic write, `.bak` kept, audited as `agent_mcp_entry_removed`).
- **Adopt into Coffer**: Coffer registers the entry as an `mcp_server` resource, checks that it reads back, and only then removes the direct entry. Any failure rolls the new resource back and leaves the agent's file byte-identical. The server is then served to every agent through the gateway. Adopting from the detail page opens the new managed server's page.

```sh
coffer scan --agent claude-code                       # direct MCP entries have kind "mcp"
coffer scan --ref claude-code:github --source global  # one entry in full, secrets withheld
coffer discard mcp claude-code:old-server --source settings
coffer adopt mcp claude-code:github --secret GITHUB_TOKEN=github/token
```

The ref is `<agent>:<entry>`, as the scan prints it.

When the entry's environment or headers carry a non-empty value under a secret-looking key (containing `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `APIKEY`, `CREDENTIAL` or `AUTHORIZATION`), adoption requires a `--secret KEY=REF` mapping for each one. Coffer stores the current value in its [encrypted secret store](/guides/secret-store) under the ref you name, and the new resource config carries only the ref. A name collision is refused with a suggested alternative (`--name` to pick one). For a Claude Code name that appears in both files, pass `--source` with the file's key (`global` or `settings`). The `coffer` entry itself is never removable or adoptable this way.

## Plugins

The **Plugins** tab lists installed plugins (all the agent's own; the owner filter is the same as on the other list tabs) with their version, marketplace, enabled switch and **Uninstall**. A plugin whose cache directory is gone is marked **Cache missing**; Coffer does not try to repair it.

Click a plugin's name to open its detail page. It shows the plugin's `<name>@<marketplace>` id, version, author, description and homepage, the marketplace it came from, and the directory it is installed in, with **Open in editor** and **Reveal** buttons. Below that it lists everything the plugin contributes, read from its package's default locations:

| Contents | Read from |
| --- | --- |
| Skills, with their descriptions | `skills/<name>/SKILL.md` |
| Commands, with their descriptions | `commands/*.md` |
| Subagents, with their descriptions | `agents/*.md` |
| Hook events | `hooks/hooks.json` |
| MCP servers | `.mcp.json` |

The page header has the same enabled switch and **Uninstall** as the tab. After an uninstall the page returns to the agent's Plugins tab; the title bar's back arrow does the same. The page only reads the plugin's files; it changes nothing.

```sh
coffer agent plugin list claude-code
coffer agent plugin show claude-code formatter@acme
coffer agent plugin disable claude-code formatter@acme
coffer agent plugin enable claude-code formatter@acme
coffer agent plugin rm codex formatter@acme
```

| | Claude Code | Codex |
| --- | --- | --- |
| Inventory read from | `plugins/installed_plugins.json`, `known_marketplaces.json` | `[plugins."…"]` and `[marketplaces.*]` in `config.toml` |
| Enable/disable writes | `enabledPlugins` in `settings.json` only | the plugin's own `enabled` field only |
| Uninstall | runs `claude plugin uninstall <id>` | removes the entry from `config.toml` and deletes `plugins/cache/<marketplace>/<plugin>/` |

Claude Code's own inventory files are never written by Coffer. When the `claude` CLI is not on `PATH`, uninstall is unavailable (`PLUGIN_UNINSTALL_UNSUPPORTED`) and the web UI hides the action. Installing plugins and managing marketplaces stay with the agent's own tooling.

## Hooks

The **Hooks** tab lists every hook the agent will run in one table (owner filter as above), read straight from the agent's files: each hook's matcher, its command and where it comes from — one of the agent's own settings files, or a plugin (by name). Only plugins that are switched on are included, since a disabled plugin's hooks do not run. Hooks set in a project's own settings are not shown, because Coffer does not know which repositories you use the agent in.

| | Claude Code | Codex |
| --- | --- | --- |
| Agent's own files | `settings.json`, `settings.local.json` | `hooks.json` |
| Plugins | each enabled plugin's `hooks/hooks.json` | each enabled plugin's `hooks/hooks.json`, where it has one |
| Coffer's own hook | `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse` in `settings.json` | the same four events in `hooks.json` |

Coffer's own hook — the [memory delivery hook](/guides/memory#install-the-hook) — is marked on each of its four entries and reported as one hook. On the tab it is a single row: the Event column reads **Memory hook · 4 events** with a chip for each event it sits on, and the summary above the table counts it once. Its state says how it is doing:

- **Current** — installed on exactly the four events, each with exactly the command this version of Coffer writes.
- **Out of date** — Coffer's hook is there but carries another command than the one Coffer writes now, or sits on another set of events. The daemon rewrites it on its next reconcile pass; **Repair** does it now.
- **Missing** — no Coffer hook. **Repair** connects the agent to Coffer again, which installs it.

For Codex it also says whether Codex will run the hook. Codex skips an entry you have not approved, and Coffer's hook counts as trusted only when all four entries are, so **Needs approval in Codex** (or **Needs re-approval in Codex**, after a Coffer update changed the command) means at least one entry is installed but not running. Open Codex, run `/hooks` and trust each of Coffer's four entries. Coffer does not approve them for you.

It also shows when the hook last fired, from the [audit log](/guides/activity). "Never fired" on an agent you use every day is the sign that the agent is not running the hook.

Everything else on the tab is read only: Coffer never edits another tool's hooks. Each row's **Open file** opens the file that declares it in your editor.

```sh
coffer agent hooks claude-code
# * SessionStart [startup|resume|clear|compact]  (user)  : coffer-memory; coffer memory hook …
# * UserPromptSubmit  (user)  : coffer-memory; coffer memory hook …
# * PreToolUse [Bash]  (user)  : coffer-memory; coffer memory hook …
#   PreToolUse [Bash]  (user)  ./lint.sh
# * PostToolUse [Bash]  (user)  : coffer-memory; coffer memory hook …
#   SessionStart  (plugin formatter@acme)  ./plug.sh
# coffer hook: current on PostToolUse,PreToolUse,SessionStart,UserPromptSubmit, last fired 2026-09-29T08:12:03Z

coffer agent hooks claude-code --json   # the full answer, with each hook's file
```

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

`coffer agent models` takes the agent's type. When the [model provider](/guides/providers) the agent runs on curates a model list, pickers offer that list instead.

The agent record carries the model binding that provider projection writes into the agent's config:

```sh
coffer agent edit claude-code --model sonnet --effort high --tier haiku=haiku
coffer agent edit claude-code --clear-tiers
coffer agent edit codex --model gpt-5.5
```

A change takes effect on disk the next time the agent's provider is switched.

## Model, native memory and sessions in the web UI

The agent page is addressed by the agent's type (`/agents/claude_code`, `/agents/codex`) and has nine tabs, each at its own address: **Overview** (`/agents/<type>`), **Model**, **Skills**, **MCP servers**, **Plugins**, **Hooks**, **Config files**, **Memory** and **Sessions** (`/agents/<type>/model`, `…/skills`, `…/mcp-servers`, `…/plugins`, `…/hooks`, `…/config`, `…/memory`, `…/sessions`). Overview shows the Coffer connection, one summary row per installed kind (each opening its tab), the model, the details — type, config directory, uid, registered — and the recent sessions; an agent's name is its type, so there is no name or title to edit.

The **Model** tab is the one place an agent's provider is switched: the built-in login or a compatible connection, the model, the effort levels that model reports, and — for Claude Code on a connection — the model per tier (Opus, Sonnet, Haiku, and Fable when the connection lists one), prefilled with suggestions. A connection must pass **Test connection** first; the review pane lists what Coffer will write before **Confirm switch**.

### Native memory and sessions

The **Memory** tab lists the agent's own memory stores, read-only:

- **Claude Code:** one store per project at `<config_dir>/projects/<slug>/memory/`, labelled with the real project directory.
- **Codex:** the global `<config_dir>/memories/MEMORY.md`, split into one row per project it routes task groups to.

Opening a row shows the store's files with a read-only preview. The memory delivery hook is part of the agent's [Coffer connection](#connect-an-agent-to-coffer), not this tab.

The **Sessions** tab lists the agent's own CLI sessions — its local transcripts (`<config_dir>/projects/**/*.jsonl` for Claude Code, `<config_dir>/sessions/**/*.jsonl` for Codex) with title, project, message count and activity times, searchable and sortable. Choosing one opens it beside the list as a conversation with a **Contents** list of your prompts; the harness's own injected blocks are folded under **Harness context**.

```sh
coffer path agent claude-code memory                   # the native memory stores
coffer path agent claude-code transcripts              # the transcript folders
coffer agent transcript claude-code -q "release" --sort message_count
coffer agent transcript claude-code <session_id> --limit 50
```

Native memory stores are plain files; read them with your own tools at the paths `coffer path` prints.

Transcript text is secret-scrubbed before it is shown, long turns are cut and flagged, and a session is read in windows of turns. Coffer never writes, stores or sends transcripts or native memory anywhere.

## Skills on an agent

The **Skills** tab lists, in one table with the owner filter, the skills Coffer delivers to the agent and the skill folders of its own that Coffer does not manage. An own folder opens a read-only preview and offers **Adopt** into Coffer's library; one named like a skill Coffer delivers offers **Remove duplicate**, which deletes the agent's copy after a confirmation. Which skills reach the agent is decided per skill; see [Skills](/guides/skills).

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| **Connect to Coffer** fails naming `coffer-mcp-shim` | The daemon cannot find the shim | Set `COFFER_MCP_SHIM_PATH` in the daemon's environment, or reinstall Coffer so `~/.coffer/bin/coffer-mcp-shim` exists. |
| Status says **Connected** but the agent has no Coffer tools | The agent was not restarted, or reads a different config directory | Restart the agent. For a custom directory, start the agent with `CLAUDE_CONFIG_DIR` / `CODEX_HOME` pointing at it. |
| **Availability** shows **Not found** | The agent's CLI (`claude` or `codex`) is not on the daemon's `PATH` | Install the CLI, or make it visible to the daemon. |
| The agent reads **Not installed** | Its program is not on your login shell's `PATH`; only its config directory is left | Reinstall the agent, or put its program on your `PATH`. |
| Detected as **Installed, never run** | The program is installed but has never created its config directory | Add it anyway: registering at the standard directory creates it. |
| Add is refused with `AGENT_TYPE_REGISTERED` | An agent of that type is already registered; there is one per type | To use another directory, run `coffer agent edit <name> --config-dir <dir>` instead. |
| A save fails with `CONFIG_FILE_STALE` | The file changed after you opened it | Re-open the file and save again. |
| Plugin uninstall is missing | `claude` is not on `PATH` | Run `claude plugin uninstall <id>` yourself. |

## Related

- [Connect a client](/guides/connect-a-client) — the shim, the HTTP endpoint and agent identity
- [MCP servers](/guides/mcp-servers) — what the gateway serves to agents
- [Model providers](/guides/providers) — projecting an endpoint into an agent
- [Agent facets](/architecture/agent-facets) — how Coffer keeps what differs between agents in one place
- [Resource framework](/architecture/resource-framework) — reach and immutable uids
- Spec: [agent-registry](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/spec.md), [claude-code](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/claude-code/spec.md), [codex](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/codex/spec.md)
