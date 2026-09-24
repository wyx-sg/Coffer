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
| [`coffer__recall`](#coffer-recall) | Locate distilled memory notes by literal match. | The `memory` feature is on. |
| [`coffer__diagnose`](#coffer-diagnose) | Read Coffer's recent audit log and daemon log. | Always. |
| [`coffer__search_tools`](#coffer-search-tools) | Rank the upstream tool catalogue against an intent. | Always. |

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

Every enabled collection is writable by every agent. Empty or whitespace-only values for a
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

## coffer\_\_recall {#coffer-recall}

Locates notes in Coffer's memory, the notes distilled from what the developer's agents have
learned. It answers with each note's absolute file path, title and one-line description;
the agent reads the file itself for the body. Matching is literal and case-insensitive,
over each note's title, description, body and search terms, so a distinctive word or phrase works and
a whole question does not. Recall spans every enabled memory partition.

Gated by the `memory` feature. Guide: [Memory](/guides/memory).

### Input

| Property | Type | Required | Description |
| --- | --- | --- | --- |
| `query` | string | yes | The word or phrase to look for. Matched literally, case-insensitively. |

An empty `query` fails with `ValueError: 'query' must be a non-empty string`. At most 10
notes are returned.

### Result

```json
{
  "notes": [
    {
      "path": "/Users/you/.coffer/memory/billing-service/notes/pnpm-workspace-hoisting.md",
      "title": "pnpm workspace hoisting",
      "description": "Why the build fails when a package is not hoisted",
      "type": "feedback",
      "partition": "billing-service"
    }
  ]
}
```

### Example call

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "method": "tools/call",
  "params": { "name": "coffer__recall", "arguments": { "query": "hoisting" } }
}
```

## coffer\_\_diagnose {#coffer-diagnose}

Reads Coffer's own recent history when something has gone wrong with it: a tool call that
failed, a credential that would not resolve, a server that stopped answering, an agent
whose config changed. It returns two timelines, newest first: what **changed** (the audit
log: registrations, deletions, credential reads, config writes, provider switches) and what
**happened** (the daemon log, including errors and tracebacks). Read-only; it returns no
secret values.

Always present. Background: [Observability](/architecture/observability).

### Input

All properties are optional.

| Property | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| `since_minutes` | integer | `60` | 1–10080 | How far back to look. |
| `errors_only` | boolean | `false` | | Keep only error-level log records (and lines whose level cannot be read). Tracebacks ride with their record. The audit side is unaffected. |
| `event_type` | string | | | Filter the audit side to one event type, for example `credential_read` or `resource_deleted`. |
| `resource_kind` | string | | | Filter the audit side to one kind, for example `mcp_server`. |
| `resource_name` | string | | | Filter the audit side to one resource by its current name. Requires `resource_kind`. Returns the resource's whole trail, including entries written under earlier names. |
| `limit` | integer | `40` | 1–200 | Maximum entries per timeline. |

Out-of-range numbers are clamped. `resource_name` without `resource_kind`, or a name that
matches nothing, fails with a message explaining how to adjust the filter; it never falls
back to an unfiltered answer.

### Result

```json
{
  "window_minutes": 60,
  "changes": [
    {
      "at": "2026-09-24T09:41:12.004211+00:00",
      "event": "credential_read",
      "resource_kind": "mcp_server",
      "resource": "jira",
      "actor": "cli",
      "details": {}
    }
  ],
  "log": [
    {
      "event": "http.unhandled_exception",
      "logger": "coffer.surfaces.http.errors",
      "level": "error",
      "timestamp": "2026-09-24T09:41:12.118420Z",
      "path": "/api/v1/resources",
      "trace_id": "5f0c2d9e8a1b4c77"
    }
  ],
  "note": "changes = the audit log (what changed, and who changed it); log = the daemon log (what happened, including failures). Both newest-first. Neither carries secret values."
}
```

`log` entries are the daemon's JSON log records as written, so their fields vary by event.

### Example call

```json
{
  "jsonrpc": "2.0",
  "id": 9,
  "method": "tools/call",
  "params": {
    "name": "coffer__diagnose",
    "arguments": { "since_minutes": 15, "errors_only": true }
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
| Built-in tool | `coffer__<tool>` | `coffer__diagnose` |

The separator is a double underscore, and a name splits on the first one: a server name
never contains `__`, an upstream tool name may. The `coffer__` prefix is reserved for
Coffer's own tools.

A call is refused, with JSON-RPC error code `-32000` and a message naming the reason, when:

- the capability is switched off on its server (the **Tools** tab of the server's page
  under **MCP servers**, or `coffer mcp tool disable`), or
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
session's list carries. With every feature on, it reads:

```text
Coffer is this machine's local vault: it aggregates the user's MCP servers behind one
endpoint, holds what this developer has written down, and adds its own tools —
coffer__write (file a durable fact about this environment), coffer__recall (locate
Coffer's distilled notes), coffer__diagnose (Coffer's own logs), coffer__search_tools
(describe an upstream tool you want in plain language; whatever comes back is callable
by name). Its knowledge is markdown you read with your own file tools. The coffer-guide
skill is the manual: load it for the catalogue of what is there, with paths, before
asking the developer something they may already have written down.
```

(Line breaks added here; the text is one paragraph.) When the `knowledge` feature is off,
the knowledge sentences are left out and the text ends with "The coffer-guide skill is the
manual: load it before relying on these tools." When tiering hid tools in this session's
last `tools/list`, one sentence is appended:

```text
Your tool list is a budgeted slice: 88 further upstream tools are not listed, and every
one is still callable.
```

## Related

- [Connect a client](/guides/connect-a-client) — install Coffer's MCP entry into an agent.
- [MCP servers](/guides/mcp-servers) — register the upstream servers these names come from.
- [MCP gateway](/architecture/mcp-gateway) — sessions, the shim, discovery and tiering in depth.
- [mcp-gateway spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/mcp-gateway/spec.md)
