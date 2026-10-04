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

A machine has at most one registered agent of each type, and the agent's name **is** its type: `claude-code` or `codex`. You do not choose a name, and an agent has no title or description. Everywhere Coffer asks which agent you mean — the reach of a skill or MCP server, and every `/api/v1/agents/{uid}/…` route — you can give the type (`claude-code`; `claude_code` also reads) or the agent's uid.

Besides its type, the only setting an agent has is its **config directory**, plus the [model binding](#models). Registering uses the type's standard directory (`~/.claude`, `~/.codex`) unless you say otherwise. Pointing Coffer at a different directory moves the one agent there; it never adds a second one. Registering a type that is already registered is refused with `409 AGENT_TYPE_REGISTERED`.

::: info The agent's files are the source of truth
Coffer never copies an agent's configuration into its own store. Config files, MCP entries, plugins, native memory and transcripts are read from disk every time you look at them. The agent record itself holds only the type, the config directory and the model binding.
:::

## Register an agent

### From detected agents

Coffer detects an agent from two signals: its program on your `PATH` — the `PATH` your login shell gives you, so an agent installed with Homebrew or a Node version manager is found even when the daemon was started from the Dock — and its config directory. It reads the program's version (`claude --version`, `codex --version`) along the way. It never registers anything on its own, and the daemon does not auto-register agents at startup.

Coffer reports every supported type, registered or not, in one of these states:

| State | Program | Config directory | What you can do |
| --- | --- | --- | --- |
| **Installed** | found | present | Connect it. |
| **Installed, never run** | found | not yet created | Connect it. Registering it at its standard directory creates that directory, holding only what Coffer needs there (its `skills` folder). |
| **Not installed** | missing | present | Nothing to add: the directory is left from an earlier install. Reinstall the agent, or ignore it. |
| **Missing** | missing | absent | Nothing on this machine. The type is still listed, so every type always has a row. |

For each type Coffer looks at its standard directory and, when the daemon's environment sets the type's own variable (`CLAUDE_CONFIG_DIR` for Claude Code, `CODEX_HOME` for Codex), at the directory that names. That second directory is never a second agent: when the standard one exists it is offered as **use a different config directory** for the one agent, and when only the named one exists it is the directory Connect registers. Coffer does not search the rest of your disk; to use any other directory, see [Use a different config directory](#use-a-different-config-directory). A type already registered is not offered again.

**Web UI:** the **Agents** page always has exactly two rows, Claude Code then Codex, whether or not each is installed. Detection is automatic — when the page opens, when the window regains focus, and every few minutes — so there is no Detect button and no Add-agent dialog. Each row reads one state and offers the one action it calls for:

| Row reads | Meaning | Action |
| --- | --- | --- |
| **Not connected** | installed, and Coffer has not connected it — a newly found agent and one you disconnected read the same | **Connect** |
| **Connected** | Coffer's entry and hook are in the agent | none |
| **Needs repair** | part of the connection is missing | **Repair** |
| **Config left behind** | a directory with no program on `PATH` | none; **Copy prompt** (the reinstall hand-off) heads the row's **⋯** menu |
| **Not installed** | neither | none; **Copy prompt** (the install hand-off) heads the row's **⋯** menu |

A row whose agent is not installed shows no version, and says **Not on this Mac** or what is left in the directory under its name. **Overview** lists only the agents that need you: one that needs repair, one whose config directory is left behind, and one whose memory hook the agent has not approved or has never run. A hook problem is one row per agent: an unapproved hook reads as the hook-approval row, and only a hook the agent runs but that has never fired reads as never fired. An agent that is merely not connected, or not installed, is never listed, and neither is a first run.

Coffer does not install agents, and installing one depends on the machine, so a row whose program is not found hands the job to an agent instead of naming an install command. **Copy prompt**, at the top of the row's **⋯** menu, copies a prompt the daemon writes: install (or reinstall) this agent on this machine, keep its existing config directory, make sure its program is found on the `PATH` Coffer looks on (the prompt lists it) and confirm with `claude --version` or `codex --version`, then come back and choose **Check again** — leaving the login to you. Paste it into any assistant. While another managed agent is available, the menu also offers **Ask an agent**, which opens a new conversation with the prompt in the composer, unsent. The agent's page offers the same prompt on its Overview tab's problem states. You can still install the agent yourself the way its maker documents; the row updates on its own once the program is on your `PATH`.

**Connect** on a newly found agent registers it at its standard directory and connects it. It first opens **Review changes** — every file it will write and the lines it adds — and writes nothing until you apply it. On a first run with both agents installed and neither connected, **Connect both** reviews and connects the two in one confirmation. A registered row also shows its provider — the Coffer connection it runs on, or its built-in login — its default model, read from the agent's own config (**Built-in default** when that names none, so the agent runs whatever its maker defaults to), and how many skills, MCP servers and plugins reach it, and opens the agent's page. A line under the table says what the counts mean.

### Use a different config directory

Claude Code reads another directory when started with `CLAUDE_CONFIG_DIR`, Codex when started with `CODEX_HOME`. If that is how you run an agent, tell Coffer the directory, at registration or later.

For an agent that is already registered, the same menu entry moves it.

**Web UI:** choose **Use a different config directory…** from the row's **⋯** menu (or the agent page's). Pick the folder with the native folder dialog (an in-app browser only where the host has none); the dialog lists which of the type's usual files are there. For an agent that is not added yet, **Use this directory** registers it there without connecting it. For a connected agent the button reads **Review changes**: the agent carries Coffer's `coffer` entry and memory hook in its directory, so moving it takes both out of the old directory and writes them into the new one, and you see those lines before anything moves.

Before accepting the directory, Coffer creates `<config_dir>/skills`, then checks that the directory exists, is a directory, is writable, and is not a system location (`/etc`, `/usr`, `/var` outside `/var/folders/`, `/System`, `C:\Windows`, `C:\Program Files` and similar). A rejected registration leaves nothing behind. A directory other than the standard one must already exist; only the standard directory of an installed, never-run agent is created for you. Moving an agent re-delivers its skills to the new directory.

When Coffer itself starts an agent registered on a directory other than the standard one — a [chat](/guides/chat) or [channel](/guides/channels) turn, a model-list probe, a plugin uninstall — it sets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` to that directory, so the agent reads the skills, MCP entry and settings Coffer put there.

### Edit and disconnect

The **⋯** menu on an agent's row and on its page carries **Use a different config directory…**, **Reveal config directory**, **Copy uid**, and **Disconnect…** (while any part is installed). There is no **Remove**: the list always holds a row for both supported agents, and disconnecting is how you take Coffer's entry and hook out of one.

- **Edit** changes the config directory or the [model binding](#models). The name is the type and cannot change. Everything that refers to an agent — reach lists, a channel's default agent, the installed MCP entry — holds the agent's immutable `uid`.
- **Disconnect…** removes Coffer's gateway entry and memory hook from the agent and leaves everything else in its files as it was (see [Connect an agent to Coffer](#connect-an-agent-to-coffer)). The agent stays registered, so the skills [reach](/guides/skills) grants it keep being delivered.

## Connect an agent to Coffer

Connecting writes everything Coffer needs into the agent's own config, in one action:

| Part | What it does | When |
| --- | --- | --- |
| Gateway MCP entry | A `coffer` stdio MCP server entry pointing at `coffer-mcp-shim`. The agent reaches every enabled upstream server, Coffer's own tools, and its delivered knowledge through it. | Always |
| Memory delivery hook | Two hook entries — session start and each prompt — through which Coffer hands the agent its memory. See [Memory](/guides/memory#install-the-hook). | Always |

Disconnecting removes both, and only Coffer's own entries; everything else in those files stays as it was.

**Web UI:** the Overview tab's **Connection** section shows each part — the MCP entry and the memory hook, with the file each lives in and whether it is current — and carries the one fix the agent's state calls for at the section's title: **Connect** when it is not connected, **Repair** when it needs repair, and **Check again** while Codex has not approved Coffer's hook. A connected agent has no button there; **Disconnect…** is in the ⋯ menu. The page header never changes into a fix button: it holds the agent's mark, its name, one status pill (**Connected**, **Not connected**, **Needs repair**, **Hook not approved** or **Config left behind**), **New conversation** and the ⋯ menu. On the **Agents** list the row carries the same state and the same action. Every connect, repair and disconnect opens the same **Review changes** preview first: a repair lists only the missing parts, a disconnect only the lines it removes. If a write fails partway, the preview says which change failed, keeps the ones that applied, and offers to retry only the failed one.

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

The memory hook's two entries are described in [Filesystem](/reference/filesystem).

Connecting is idempotent: connecting again rewrites each entry in place and never adds a second one. Disconnecting when nothing is installed succeeds and changes nothing. Every write is backed up and audited by part (`agent_mcp_installed` / `agent_mcp_uninstalled`, `memory_delivery_installed` / `memory_delivery_removed`). The connection status is read from the files each time; Coffer does not store it.

### Why the shim path is absolute

The daemon may run from the desktop app, a login service or a virtualenv, none of which inherit your shell's `PATH`, and the agent may not either. Coffer therefore writes the full path. It resolves the shim in this order:

1. `COFFER_MCP_SHIM_PATH`, if set and the file exists;
2. `coffer-mcp-shim` on the daemon's `PATH`;
3. the scripts directory of the Python interpreter running the daemon (where `pip` and `uv` put console scripts);
4. the binary bundled beside the running executable.

When the answer is the installed build, Coffer writes the stable `~/.coffer/bin/coffer-mcp-shim` link rather than a versioned directory, so the entry survives upgrades. If no shim can be found, install fails with `SHIM_NOT_FOUND`, naming the missing binary, and writes nothing. The refusal carries a hand-off prompt that lists every place Coffer looked and asks an agent to find or reinstall the shim so it resolves at `~/.coffer/bin/coffer-mcp-shim`: the Connect review offers it as **Copy prompt** beside **Retry**.

### The agent uid and reach

The `--agent-uid` argument is how the gateway knows which agent a session belongs to. The shim passes it in the MCP `initialize` handshake, and the gateway uses it for the whole session to decide which servers the agent may see. A server whose [reach](/architecture/resource-framework) names only certain agents is hidden from every other session.

The entry carries the uid because Coffer writes it once into a file it does not otherwise revisit, and the uid is the identity every other record holds. A hand-written shim entry without `--agent-uid` still works, but its session is unidentified and sees only servers that reach every agent. See [Connect a client](/guides/connect-a-client) for the details.

## What Coffer reads and what it writes

Coffer touches an agent's files through a short list of documented surfaces:

| Surface | Coffer reads | Coffer writes |
| --- | --- | --- |
| Allowlisted config files | yes | yes, when you save in the editor |
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

Reading a file that does not exist returns empty content and does not create it. Files inside a directory entry must stay inside it and end in `.md`.

::: tip Concurrent edits are refused, not overwritten
Every read returns a fingerprint of the content. The editor sends it back with the save, and if the file changed on disk in the meantime — the agent itself rewrote it, or you saved it elsewhere — the write is refused with `CONFIG_FILE_STALE` and the file is left as it is. Re-open and save again.
:::

## Manage the agent's own MCP entries

Agents often carry MCP servers configured directly in their own files. The **MCP servers** tab opens with what Coffer manages — one **From Coffer** row that says how many registered servers reach this agent through the gateway entry, names the first few and links to **Open MCP servers ›**, the MCP servers page narrowed to this agent (`/mcp-servers?agent=<uid>`) — and then shows **the agent's own MCP servers**: the direct entries in its files, with a search. Coffer's servers are not listed one by one here. An own entry offers **Adopt**; one that duplicates a registered MCP server offers **Remove duplicate**, which takes it out of the agent's file because the gateway already serves it. A second **From Coffer** row counts the custom-tool groups that reach this agent and links to **Open Custom tools ›**, the [Custom tools](/guides/custom-tools) list narrowed to this agent (`/custom-tools?agent=<uid>`); the first row counts registered MCP servers only. A row has at most one button; **Remove…**, which takes any entry out of its file, is in its **⋯** menu.

| Type | Direct entries are read from |
| --- | --- |
| Claude Code | `mcpServers` in `.claude.json` (the `global` file) and in `settings.json` |
| Codex | `[mcp_servers.*]` in `config.toml` (the `enabled` flag is shown but never written) |

Click a direct server's name to open its entry in a dialog. It shows, read-only, everything the agent's file holds for that server: the transport, the command and each argument (or the URL), the working directory, the `enabled` flag where the format has one, the names of its environment variables and HTTP headers, any other keys the entry carries, and the config file it lives in. Secret values never leave the daemon: environment and header values are shown only as *set* or *secret · hidden*, and any other key whose name looks secret (the pattern below) shows as *hidden*. Coffer does not start a direct server to show this, so it lists no tools. The dialog's footer carries the two actions of the row around **Close**: **Remove** (or **Remove duplicate**) on the left, **Adopt** on the right.

You can do two things with a direct entry:

- **Remove** it from its source file (atomic write, `.bak` kept, audited as `agent_mcp_entry_removed`).
- **Adopt**: Coffer registers the entry as an `mcp_server` resource, checks that it reads back, and only then removes the direct entry. Any failure rolls the new resource back and leaves the agent's file byte-identical. The server is then served to every agent through the gateway.

When the entry's environment or headers carry a non-empty value under a secret-looking key (containing `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `APIKEY`, `CREDENTIAL` or `AUTHORIZATION`), the Adopt dialog lists each one under **Store as**, preset to **Secret**. Coffer stores the current value in its [encrypted secret store](/guides/secret-store), and the new resource config carries only a reference. A name collision is refused: choose another **Name in Coffer**. For a Claude Code name that appears in both files, the entry you opened is the one adopted. The `coffer` entry itself is never removable or adoptable this way.

## Plugins

The **Plugins** tab, behind **More** in the tab strip, lists installed plugins — all the agent's own, since Coffer installs none — with a search, their version and marketplace, an enabled switch and a **⋯** menu whose one item is **Uninstall…**. A plugin whose cache directory is gone is marked **Cache missing**, and puts a warning dot on **More**; Coffer does not try to repair it.

Click a plugin's name to open its information dialog. It shows the plugin's `<name>@<marketplace>` id, version, author, description and homepage, the marketplace it came from, and the directory it is installed in, with **Open in editor** and **Reveal** buttons. Below that it lists everything the plugin contributes, read from its package's default locations:

| Contents | Read from |
| --- | --- |
| Skills, with their descriptions | `skills/<name>/SKILL.md` |
| Commands, with their descriptions | `commands/*.md` |
| Subagents, with their descriptions | `agents/*.md` |
| Hook events | `hooks/hooks.json` |
| MCP servers | `.mcp.json` |

The dialog only reads the plugin's files; it changes nothing. Enabling and uninstalling are on the tab.

| | Claude Code | Codex |
| --- | --- | --- |
| Inventory read from | `plugins/installed_plugins.json`, `known_marketplaces.json` | `[plugins."…"]` and `[marketplaces.*]` in `config.toml` |
| Enable/disable writes | `enabledPlugins` in `settings.json` only | the plugin's own `enabled` field only |
| Uninstall | runs `claude plugin uninstall <id>` | removes the entry from `config.toml` and deletes `plugins/cache/<marketplace>/<plugin>/` |

Claude Code's own inventory files are never written by Coffer. When the `claude` CLI is not on `PATH`, uninstall is unavailable (`PLUGIN_UNINSTALL_UNSUPPORTED`) and the web UI hides the action. Installing plugins and managing marketplaces stay with the agent's own tooling.

## Hooks

The **Hooks** tab shows every hook the agent will run, read straight from the agent's files: each hook's event, matcher, command and where it comes from — one of the agent's own settings files, or a plugin (by name). Only plugins that are switched on are included, since a disabled plugin's hooks do not run. Hooks set in a project's own settings are not shown, because Coffer does not know which repositories you use the agent in. It has two parts, Coffer's first.

| | Claude Code | Codex |
| --- | --- | --- |
| Agent's own files | `settings.json`, `settings.local.json` | `hooks.json` |
| Plugins | each enabled plugin's `hooks/hooks.json` | each enabled plugin's `hooks/hooks.json`, where it has one |
| Coffer's own hook | `SessionStart` and `UserPromptSubmit` in `settings.json` | the same two events in `hooks.json` |

**Coffer's memory hook** — the [memory delivery hook](/guides/memory#install-the-hook) — is marked on each of its two entries and reported as one hook, as a block of properties at the top: its state and when it last fired, its command, the events it sits on and the file that declares it. Its fix is at the block's title (**Repair**, or **Check again**), and the reason a state is a problem is written in the block. The state says how it is doing:

- **Current** — installed on exactly the two events, each with exactly the command this version of Coffer writes.
- **Out of date** — Coffer's hook is there but carries another command than the one Coffer writes now, or sits on another set of events. The daemon rewrites it on its next reconcile pass; **Repair** does it now.
- **Missing** — no Coffer hook. **Repair** connects the agent to Coffer again, which installs it.

For Codex it also says whether Codex will run the hook. Codex skips an entry you have not approved, and Coffer's hook counts as approved only when both entries are, so **Not approved** (or **Changed since trusted**, after a Coffer update changed the command) means at least one entry is installed but not running. The agent's page reads **Hook not approved**, and Overview lists it under **Needs you**. Open Codex, run `/hooks` and trust both of Coffer's entries. Coffer does not approve them for you, and **Check again** re-reads Codex's approval afterwards.

It also shows when the hook last fired, from the [audit log](/guides/activity). **Never fired** on an agent you use every day is the sign that the agent is not running the hook; the block says the likely cause and links to **Activity**, and Overview lists it under **Needs you**.

**The agent's own hooks** are one table of **Event**, **Command**, **Matcher** and **File**, without Coffer's hook, with a search over the command and an **Event** filter that shows how many hooks each event has; once either narrows the table it says how many of how many are shown. Click a row for its details: the command in full, the event and when it runs, the matcher, the type, the timeout, the file and the entry's position in it (`hooks.<event>[group].hooks[hook]`), with **Copy command** and **Open in Config files**. Everything on the tab is read only: Coffer never edits another tool's hooks, so a hook is changed in its own file, and a file name opens that file in **Config files**.

## Models

The model catalogue answers "which models can this agent be put on". Coffer reads it back from the installed agent every time, so a newly released model appears without a Coffer release:

- **Claude Code:** the model aliases embedded in the `claude` binary (for example `opus`, `sonnet`, `haiku`), plus `additionalModelOptionsCache` from `.claude.json`. Reasoning-effort levels come from the installed Claude Agent SDK; no default level is reported, because the runtime does not publish one.
- **Codex:** the `model/list` RPC of Codex's app server (run with `CODEX_HOME` set to the agent's directory), plus the models named in `config.toml`. Each model carries its own effort levels and default.

Each source fails on its own: an unauthenticated Codex or a changed binary layout costs only that source's models.

When the [model provider](/guides/providers) the agent runs on curates a model list, pickers offer that list instead.

The agent record carries the model binding that provider projection writes into the agent's config. It is changed from the agent's Overview, with **Change…** under **Model**, which shows the lines before it writes them (see [The agent page](#the-agent-page-in-the-web-ui)).

## The agent page in the web UI

The agent page is addressed by the agent's type (`/agents/claude_code`, `/agents/codex`). Its header holds the agent's mark, its name, one status pill, **New conversation** and a **⋯** menu — no line under the name — and it never turns into a fix button. Below it are eight tabs, none carrying a count. Six sit in the strip, each at its own address: **Overview** (`/agents/<type>`), **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** (`…/skills`, `…/mcp-servers`, `…/hooks`, `…/config`, `…/sessions`). **More** holds the two least used, **Plugins** and **Memory** (`…/plugins`, `…/memory`); while one of them is open, **More** reads its name and carries the underline, and a warning dot on **More** says a tab inside it needs a look. There is no Model tab.

**Overview** is one column, top to bottom:

1. **Connection** — the two parts of the [connection](#connect-an-agent-to-coffer) and the one button the state calls for.
2. **What this agent can use** — six tiles, three by two: **MCP servers**, **Skills**, **Config files**, **Plugins**, **Hooks** and **Memory**. Each shows its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; the whole tile opens its tab.
3. **Model** — **Provider**, **Model**, **Effort** and **Route** (through Coffer's proxy, with **Test**, or direct), and **Change…**.
4. **Details** — **Version**, **Config directory**, **UID** and **Registered**. An agent's name is its type, so there is no name or title to edit.

**Rotate proxy token** is in the header's **⋯** menu, offered only while the agent runs through Coffer's proxy.

### Change an agent's model

**Change…** under **Model** opens one small form for both agents. Pick a **Provider** — the agent's built-in login or an enabled provider that reaches it (see [Model providers](/guides/providers)) — then:

- **Claude Code:** **Model**, **Effort** (the levels that model reports; the field is left out when it reports none) and **Model per tier** — Opus, Sonnet, Haiku, and Fable when the provider lists one — prefilled with suggestions. It writes the agent's `settings.json`.
- **Codex:** **Model** and **Effort** (again only when the model reports levels), with no tiers. It writes `config.toml` and Coffer's own model list file `coffer-model-catalog.json` beside it, so the review shows two changes.
- **The built-in login** asks for nothing else: the agent picks its own model and effort (`/model`, `/effort`), and Coffer sets them only for a provider you add. Choosing it takes out the keys Coffer wrote.

**Review changes** then opens the exact lines each file will gain or lose, with a note that only those lines change and a `.bak` copy is kept; **Apply** writes them. While the review is computed Coffer also tests the provider with the chosen model; a failed test is shown as a warning and does not stop you. If a file changed on disk after the review was drawn — the agent rewrote it, or you edited it — Apply refuses, writes nothing, says which file changed and offers **Reload preview**. A link from a provider's **Used by** list (**Codex › Change model**) opens this form on arrival. With the Models [experimental feature](/guides/experimental-features) off, the **Model** section only reads: the agent's own model and effort, with no provider and no **Change…**.

### Native memory and sessions

The **Memory** tab lists the agent's own memory stores, read-only:

- **Claude Code:** one store per project at `<config_dir>/projects/<slug>/memory/`, labelled with the real project directory.
- **Codex:** the global `<config_dir>/memories/MEMORY.md`, split into one row per project it routes task groups to.

Opening a row shows the store's files in a file tree with a read-only preview. While the Memory [experimental feature](/guides/experimental-features) is on, the tab opens with **Coffer's memory** — Coffer's memory hook for this agent, when it last fired and what it delivers, with a link to the [Memory](/guides/memory) page and **Repair** when the hook is out of date or missing — and the agent's own stores follow.

The **Sessions** tab lists the agent's own CLI sessions — its local transcripts (`<config_dir>/projects/**/*.jsonl` for Claude Code, `<config_dir>/sessions/**/*.jsonl` for Codex) with title, project, message count and activity times, searchable and sortable. Choosing one opens it beside the list as a conversation, read-only; the harness's own injected blocks are folded under **Harness context**, so your words lead each turn. Your turns are right-aligned accent bubbles, as in Chat, and the agent's replies sit unboxed on the left under its mark, so the two sides read apart at a glance. The **Project** filter has a search box that matches the full project path, and the divider between the list and the reader can be dragged (Coffer remembers the width). A session's title is its first real prompt; attachment placeholders such as `[Image: source: …]` are left out of it, and a session that opens with nothing but an image reads as an untitled session. A session that cannot be loaded says so in the reader, with **Retry**.

Native memory stores are plain files; the **Memory** tab shows each store's folder, and you can read the files with your own tools.

Transcript text is secret-scrubbed before it is shown, long turns are cut and flagged, and a session is read in windows of turns. Coffer never writes, stores or sends transcripts or native memory anywhere.

## Skills on an agent

The **Skills** tab opens with one **From Coffer** row: how many skills Coffer delivers to the agent, the first few names, and **Open Skills ›**, which opens the [Skills](/guides/skills) page narrowed to this agent (`/skills?agent=<uid>`) — Coffer's skills are not listed one by one here. Below it, **the agent's own skills** — the skill folders Coffer does not manage — with a search. Each row carries a state word — **Unmanaged**, **Invalid SKILL.md**, **Foreign link** or **Duplicate** — and at most one button. A valid folder offers **Adopt**, which asks for the **name in Coffer** and its **reach** (every agent unless you narrow it, or off) before moving it into Coffer's library; one named like a skill Coffer delivers offers **Delete duplicate**, which deletes the agent's copy after a confirmation. A row opens the folder's own page — its properties, and its files in a tree beside a read-only viewer — whose header has **Adopt** and a **⋯** menu with **Delete…**. Which skills reach the agent is decided per skill; see [Skills](/guides/skills).

## Act on several of the agent's own items at once {#act-on-several-items-at-once}

On the **Skills**, **MCP servers** and **Plugins** tabs, the agent's own list can be acted on in bulk. Coffer's part — the **From Coffer** row — cannot. Each row has a checkbox and the box above the list selects every row the search shows; an MCP entry of a config file that does not parse has no checkbox. While rows are ticked, a bar reading "N of M selected" replaces the search box, with the actions and **Clear**; **Esc** clears the selection.

| Tab | Actions | Notes |
| --- | --- | --- |
| Skills | **Adopt**, **Delete…** | Adopt takes unmanaged folders only and asks once for a reach shared by all of them; each skill keeps its folder name. |
| MCP servers | **Adopt**, **Remove…** | Adopt takes entries that bypass Coffer only, under their own names and with the default secret references; the dialog says how many secret values move into the [secret store](/guides/secret-store). |
| Plugins | **Enable**, **Disable**, **Uninstall…** | Enable and Disable need no confirmation and skip plugins already in that state. Uninstall is disabled, with the reason, while the agent's program is not found. |

Coffer sends the same request the single-item action sends, once per item and one after another, so a name Coffer already has fails that item alone. A dialog or toast says how many ticked items an action skipped. When everything went through you get one confirmation and the selection clears; when some failed they are listed by name with the reason, and **Retry** sends only those.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| **Connect** fails naming `coffer-mcp-shim` | The daemon cannot find the shim | Set `COFFER_MCP_SHIM_PATH` in the daemon's environment, or reinstall Coffer so `~/.coffer/bin/coffer-mcp-shim` exists. |
| The agent reads **Connected** but has no Coffer tools | The agent was not restarted, or reads a different config directory | Restart the agent. For a custom directory, start the agent with `CLAUDE_CONFIG_DIR` / `CODEX_HOME` pointing at it. |
| The agent reads **Not found** | It was registered, but its CLI (`claude` or `codex`) is not on the daemon's `PATH` and its directory is gone | Install the CLI, or make it visible to the daemon. |
| The agent reads **Config left behind** | Its program is not on your login shell's `PATH`; only its config directory is left | Reinstall the agent (**Copy prompt** in its **⋯** menu), or put its program on your `PATH`. |
| Detected as **Installed, never run** | The program is installed but has never created its config directory | Connect it anyway: registering at the standard directory creates it. |
| Registering is refused with `AGENT_TYPE_REGISTERED` | An agent of that type is already registered; there is one per type | To use another directory, choose **Use a different config directory…** from the row's **⋯** menu instead. |
| A save fails with `CONFIG_FILE_STALE` | The file changed after you opened it | Re-open the file and save again. |
| Plugin uninstall is missing | `claude` is not on `PATH` | Run `claude plugin uninstall <id>` yourself. |

## Related

- [Connect a client](/guides/connect-a-client) — the shim, the HTTP endpoint and agent identity
- [MCP servers](/guides/mcp-servers) — what the gateway serves to agents
- [Model providers](/guides/providers) — projecting an endpoint into an agent
- [Agent facets](/architecture/agent-facets) — how Coffer keeps what differs between agents in one place
- [Resource framework](/architecture/resource-framework) — reach and immutable uids
- Spec: [agent-registry](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/spec.md), [claude-code](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/claude-code/spec.md), [codex](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/agent-registry/codex/spec.md)
