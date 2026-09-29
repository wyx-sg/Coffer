---
title: MCP tools reference
description: Coffer's built-in coffer__ tools, their input schemas and results, how upstream tools are named, and what the gateway tells an agent at the handshake.
---

# MCP tools reference

This page describes what an agent sees when it connects to Coffer's MCP endpoint: the
built-in `coffer__*` tools with their exact input schemas and results, the naming rules for
the upstream tools, resources and prompts Coffer aggregates, and the instructions Coffer
returns at the `initialize` handshake. It is for anyone writing prompts, skills or
integrations against Coffer. For how the gateway works internally, see
[MCP gateway](/architecture/mcp-gateway).

## At a glance

| Tool | Purpose | Present when |
| --- | --- | --- |
| [`coffer__write`](#coffer-write) | File a durable fact into Coffer's knowledge. | The `knowledge` feature is on. |
| [`coffer__search_tools`](#coffer-search-tools) | Rank the upstream tool catalogue against an intent. | Always. |

Those two are the whole list. Coffer's memory notes and its own records have no tool:
they are read with the agent's own file tools and with the `coffer` command line. See
[Memory and logs without a tool](#memory-and-logs-without-a-tool).

A tool whose [experimental feature](/guides/experimental-features) is switched off is
absent from `tools/list`, is not named in the handshake instructions, and a call to it is
answered exactly like a call to a tool that does not exist. Switching a feature takes effect
on the next list or call, without a restart.

::: tip Names inside your agent
Coffer is installed into an agent's config as an MCP server named `coffer`, so most clients
show these tools with their own prefix in front. In Claude Code, for example,
`coffer__write` appears as `mcp__coffer__coffer__write`.
:::

## How built-in tools answer

Every built-in tool returns a standard MCP `CallToolResult`:

- On success, `content` holds one `text` item with the result serialized as JSON, and
  `structuredContent` holds the same object. `isError` is `false`.
- When the tool itself fails (a missing argument, an unknown collection), the result has
  `isError: true` and a `text` item with the message, so the model can read it and correct
  the call. Coffer-authored messages are passed through; any other exception is reduced to
  its class name so no upstream content or secret can leak.
- Protocol problems (an unknown tool name, a malformed request) are JSON-RPC errors instead.

Every call, successful or not, is recorded in the MCP invocation log under the reserved
server uid `coffer`, alongside upstream calls. See [Activity and audit](/guides/activity).

The gateway also injects two arguments that are not in any public schema:

| Argument | Rule |
| --- | --- |
| `agent` | Always set by the gateway to the name of the agent that opened the session (from the shim's `--agent-uid`). A value the client sends is discarded. Used only to label audit entries. |
| `cwd` | Filled from the session's launch directory for a tool whose schema declares a `cwd` property, when the client did not send one. |

## coffer\_\_write {#coffer-write}

Records something durable about the user's working environment into a knowledge
collection: a fact about a service, a convention, a decision and its reason, a trap and how
to avoid it. What you write is new material; Coffer's curation pass merges it into the
collection's documents and deduplicates it against what is already there. It is not for
anything in the repository in front of the agent, anything transient, or secrets. There is
no read tool: agents read knowledge with their own file tools, at the paths the
`coffer-guide` skill lists.

Gated by the `knowledge` feature. Guide: [Knowledge](/guides/knowledge).

### Input

| Property | Type | Required | Description |
| --- | --- | --- | --- |
| `collection` | string | yes | Which collection to file it under. The `coffer-guide` skill names them all. |
| `title` | string | yes | Human-readable title naming the subject. |
| `description` | string | yes | One line saying what this answers. Curation reads it first when deciding where the material belongs. |
| `body` | string | no | The Markdown content. |

Every collection is writable by every agent. Empty or whitespace-only values for a
required property fail with `ValueError: 'title' must be a non-empty string` (and so on).
A collection that does not exist fails with a message that lists the collections you may
write to.

### Result

When an internal model is configured, the material is queued for curation:

```json
{
  "collection": "global",
  "title": "Staging DB is read-only on Fridays",
  "status": "pending",
  "note": "Queued as new material. Coffer's curation pass merges it into this collection's documents shortly."
}
```

With no internal model configured, the material is filed as a document of its own and the
result names it:

```json
{
  "path": "staging-db-read-only-on-fridays.md",
  "title": "Staging DB is read-only on Fridays",
  "description": "When staging writes fail at the end of the week",
  "file_path": "/Users/you/.coffer/knowledge/global/staging-db-read-only-on-fridays.md",
  "folder_path": "/Users/you/.coffer/knowledge/global",
  "status": "written",
  "note": "Filed as a document of its own: no internal model is configured to merge it."
}
```

### Example call

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": {
    "name": "coffer__write",
    "arguments": {
      "collection": "global",
      "title": "Staging DB is read-only on Fridays",
      "description": "When staging writes fail at the end of the week",
      "body": "A freeze job flips the staging primary to read-only every Friday at 18:00 UTC."
    }
  }
}
```

## coffer\_\_search\_tools {#coffer-search-tools}

Searches the aggregated catalogue of upstream MCP tools by intent and returns the most
relevant tool definitions. It is the way to reach a tool that the budgeted `tools/list` did
not include: every returned tool is callable by name, whether or not it was listed. Ranking
is deterministic BM25 over each tool's server, name and description. Coffer's own
`coffer__*` tools are excluded from the results. The search sees the whole catalogue of
servers in the session's reach; a server that fails to answer is skipped.

Always present. Background: [MCP gateway](/architecture/mcp-gateway).

### Input

| Property | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `query` | string | yes | | What you want to do, in natural language or keywords. |
| `top_k` | integer | no | `5` | How many tools to return. Clamped to 1–20. |

### Result

```json
{
  "tools": [
    {
      "name": "jira__jira_get_issue",
      "description": "Get details of a specific Jira issue.",
      "inputSchema": { "type": "object", "properties": { "issue_key": { "type": "string" } }, "required": ["issue_key"] },
      "score": 7.4213
    }
  ],
  "total_searched": 138
}
```

### Example call

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "coffer__search_tools",
    "arguments": { "query": "read a jira ticket", "top_k": 3 }
  }
}
```

## Upstream names

Coffer re-exposes the tools, resources and prompts of every enabled
[MCP server](/guides/mcp-servers) in the session's reach, namespaced by the server's name so
two servers can never collide:

| Capability | Form | Example |
| --- | --- | --- |
| Tool | `<server>__<tool>` | `jira__jira_get_issue` |
| Prompt | `<server>__<prompt>` | `github__summarize_pr` |
| Resource URI | `coffer://<server>/<original-uri>` | `coffer://docs/file:///guide.md` |
| Built-in tool | `coffer__<tool>` | `coffer__search_tools` |

The separator is a double underscore, and a name splits on the first one: a server name
never contains `__`, an upstream tool name may. The `coffer__` prefix is reserved for
Coffer's own tools.

A server's name is fixed once it is registered, because it is the prefix of every tool
name above and agents' permission rules and skills quote those names. To show a friendlier
label in Coffer, set the server's `title`; to use a different name, remove the server and
register it again. A new server's name is at most 24 characters. See
[MCP servers](/guides/mcp-servers).

### Client-visible name length

Clients add their own prefix, so an agent sees `mcp__coffer__<server>__<tool>`. Model
provider APIs refuse tool names longer than 64 characters, and Cursor drops tools longer
than 60. Coffer records that length for every discovered capability as
`client_name_length`, and the server's **Tools** tab and `coffer mcp cap list <server>`
flag each tool above 64. `mcp__coffer__` (13) plus a 24-character server name plus `__`
(2) leaves 25 characters for the upstream tool's own name.

A call is refused, with JSON-RPC error code `-32000` and a message naming the reason, when:

- the capability is switched off on its server (the **Tools** tab of the server's page
  under **MCP servers**, or `coffer mcp cap disable <server> tool:<name>`), or
- the server's [reach](/architecture/resource-framework#reach) does not include the agent
  that opened the session.

Other failures inside Coffer are JSON-RPC error `-32603`. A failing upstream tool returns
its own `isError: true` result unchanged.

### Tiering

When the upstream catalogue is larger than the listing budget, `tools/list` carries a
slice of it: Coffer's built-ins always, then upstream tools ranked by how often they were
called over a recent window, with at least one tool per server. Unlisted tools stay
callable by name and are found with `coffer__search_tools`. The budget is set by
environment variables on the daemon; see [Configuration](/reference/configuration).

| Setting | Default |
| --- | --- |
| Budget (upstream tools listed) | 50 |
| Usage window | 90 days |
| Mode | on; `COFFER_TOOL_TIERING=off` lists everything |

## Handshake instructions

Coffer's `initialize` result declares protocol version `2025-06-18`, server name `coffer`,
and the capabilities `tools`, `resources` and `prompts`, each with `listChanged: true`
(resources without `subscribe`). Its `instructions` field, which clients place in the
agent's system prompt, is at most 800 characters and names only the built-in tools the
session's list carries. With every feature on, it reads (the memory root is the
vault's own, here `/Users/you/.coffer/memory`):

```text
Coffer is this machine's local vault: it aggregates the user's MCP servers behind one
endpoint, holds what this developer wrote down, and adds its own tools: coffer__write
(file a durable fact), coffer__search_tools (describe an upstream tool you need; results
are callable by name). Its knowledge is markdown you read with your own file tools. Its
memory notes are Markdown under /Users/you/.coffer/memory/*/notes/; grep them with your
own tools. Its own logs: coffer log audit|mcp|daemon (files: coffer path logs). The
coffer-guide skill is the manual: load it for the catalogue, with paths, before asking
the developer something they may have written down.
```

(Line breaks added here; the text is one paragraph.) When the `memory` feature is off, the
memory sentence is left out. When a memory root is too long for the 800-character cap, the
sentence names the directory `coffer path memory` prints instead of the path itself. When
the `knowledge` feature is off, `coffer__write` and the knowledge sentence are left out and
the text ends with "The coffer-guide skill is the manual: load it before relying on these
tools." When tiering hid tools in this session's last `tools/list`, one sentence is
appended:

```text
Your tool list is a budgeted slice: 88 more upstream tools are unlisted, all callable.
```

## Memory and logs without a tool {#memory-and-logs-without-a-tool}

Coffer has no tool for reading its memory notes or its own records, because an agent can
already do both with what it has:

| To find | Do this |
| --- | --- |
| A memory note | Grep the memory root the handshake and the session-start delivery name (every partition's notes are `<root>/<partition>/notes/*.md`), then read the file. `coffer path memory [<partition>]` prints the root or one partition's folder. |
| What changed in Coffer (registrations, deletions, credential reads, config writes) | `coffer log audit --since 1h` |
| Which MCP calls failed | `coffer log mcp --status error --since 1h`, or `--server <name>` for one server |
| What the daemon logged, including tracebacks | `coffer log daemon --errors --since 1h`, or grep the file `coffer path logs` names |

Every `coffer log` reader takes `--json` for scripts. See
[Activity and audit](/guides/activity) and [Memory](/guides/memory).

## Related

- [Connect a client](/guides/connect-a-client) — install Coffer's MCP entry into an agent.
- [MCP servers](/guides/mcp-servers) — register the upstream servers these names come from.
- [MCP gateway](/architecture/mcp-gateway) — sessions, the shim, discovery and tiering in depth.
- [mcp-gateway spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/mcp-gateway/spec.md)
