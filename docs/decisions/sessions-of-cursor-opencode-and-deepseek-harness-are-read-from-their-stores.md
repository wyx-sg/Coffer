# Sessions of Cursor, OpenCode and DeepSeek Harness Are Read From Their Stores

**Status**: Accepted
**Date**: 2026-11-23
**Deciders**: Yuxing Wu
**Related**: [Cursor, OpenCode and DeepSeek Harness Chat Through Their One-Shot Commands](cursor-opencode-and-deepseek-harness-chat-through-their-one-shot-commands.md), [What Coffer Does for an Agent Follows From Its Facets](what-coffer-does-for-an-agent-follows-from-its-facets.md), spec agent-registry "List the sessions an agent keeps in its own store"

## Context

An agent's **Sessions** tab, and the Conversations page that merges every
agent's, list the sessions the agent keeps, from any folder. Claude Code and
Codex answer that themselves (the Agent SDK's `list_sessions`, the app-server's
`thread/list`). Once Cursor, OpenCode and DeepSeek Harness could run turns,
the owner asked for their sessions too, and chose (2026-11-23) to list the
agents' own sessions rather than only the ones Coffer ran.

What each one offers (checked on 2026-11-23 against OpenCode 1.19.6 and
2.3.2 and dsh 0.2.2-rc.5; Cursor from its documentation and the stores its
CLI writes):

| | Lists every folder's sessions | Store | Rename | Delete |
| --- | --- | --- | --- | --- |
| OpenCode | no: `opencode session list` is the current project's | SQLite `~/.local/share/opencode/opencode.db`, table `session` (1.x) or `session_v2` (2.x) | none | `opencode session delete <id>` |
| DeepSeek Harness | no command | `~/.dsh/sessions/<folder key>/<id>/` (zstd log), with a JSON projection cached under `storages/session_projcache` | none | none |
| Cursor | `cursor-agent ls` is interactive and the current folder's | `~/.cursor/chats/<folder hash>/<id>/store.db`, a SQLite file whose `meta` row is hex-encoded JSON | none | none |

How comparable tools do it: the session browsers and usage counters that span
several agents (for example `ccusage`'s OpenCode support, and the community
exporters for Cursor's CLI chats) read these stores directly, read-only,
because none of the agents offers a cross-folder listing. The agents' own UIs
read the same stores.

## Options

### A. Read each store, read-only, and fall back to Coffer's conversations (chosen)

Coffer reads the store the agent keeps, never writes it, and does only what
the agent's own command can do: OpenCode's delete, nothing else. If a new
version stores sessions in a way Coffer cannot read, the list is the
conversations Coffer ran on the agent, and the daemon log says why.

- ✅ The tab lists everything the person ran, in a terminal or through Coffer,
  as it does for Claude Code and Codex.
- ✅ Nothing Coffer does can corrupt an agent's store, and a format change
  degrades the list instead of failing it.
- ❌ The stores are not public interfaces, so a reader can break on an
  upgrade; the agent-cli CI job lists a real session after a real turn on
  OpenCode 1.x and 2.x and DeepSeek Harness, and the fallback covers the
  gap until a reader is fixed.
- ❌ Rename is not offered for any of the three, and delete only for OpenCode.

### B. List only the conversations Coffer ran

The list is the conversation index's rows for the agent.

- ✅ No dependency on any store's format.
- ❌ Sessions the person ran in a terminal never appear, which is what the tab
  exists for. The owner chose against this.

### C. Read the stores and also rename and delete by editing them

Rename by updating the title row, delete by removing the session's folder or
rows.

- ✅ Every row gets the full menu.
- ❌ Coffer would write files another program owns, with that program possibly
  running (OpenCode's TUI and DeepSeek Harness hold their sessions open; a
  write could be overwritten or corrupt a session). The agents' own commands
  are the only safe way to change their sessions, as the existing requirement
  "Rename and delete a native session through the agent" already says.

## Decision

Option A. OpenCode's database is opened read-only (`mode=ro`) and its 1.x or
2.x table chosen by name; top-level, unarchived sessions are listed, as
OpenCode's own list shows them. DeepSeek Harness's session folders are the
list, titled from the cached projection (title, else first message), with
subagent sessions left out and the log's time as the last activity. Cursor's
chats are titled from their `meta` row. Deleting an OpenCode session runs
`opencode session delete`, with `--standalone` on 2.x so the delete happens
in that one process rather than through a background service. The menu of a
row leaves out what its agent cannot do.

Building the readers found a bug in the chat driver: OpenCode takes its
project folder from `PWD`, not from the process's directory, so every turn
now runs with `PWD` set to the conversation's folder.

## Consequences

- The `sessions` feature now follows from a session source for all five
  types that run turns; Antigravity still has none.
- A reader that stops working shows Coffer's conversations instead, with a
  warning in the daemon log; fixing it is a small change to one function.
- DeepSeek Harness ships no terminal interface, so its rows do not open in a
  terminal; Cursor's and OpenCode's resume with `cursor-agent --resume` and
  `opencode --session`.
