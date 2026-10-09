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
| [`coffer__search_tools`](#coffer-search-tools) | Rank the upstream tool catalogue against an intent. | Always. |
| [`coffer__ask`](#coffer-ask) | Ask the owner a question and wait for the answer. | Only inside a turn Coffer runs. |
| [`coffer__channel_read_thread`](#coffer-channel-read-thread) | Read a chat thread's earlier messages, page by page. | Only inside a turn Coffer runs. |

Those three are the whole list. Coffer's knowledge, its memory notes and its own records have no
tool: agents change and read knowledge and memory with their own file tools, and read the
records with the `coffer` command line. See
[Knowledge, memory and logs without a tool](#memory-and-logs-without-a-tool).

::: tip Names inside your agent
Coffer is installed into an agent's config as an MCP server named `coffer`, so most clients
show these tools with their own prefix in front. In Claude Code, for example,
`coffer__search_tools` appears as `mcp__coffer__coffer__search_tools`.
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

## coffer\_\_search\_tools {#coffer-search-tools}

Searches the aggregated catalogue of upstream MCP tools by intent and returns the most
relevant tool definitions. It is the way to reach a tool that the budgeted `tools/list` did
not include: every returned tool is callable by name, whether or not it was listed. Ranking
is deterministic BM25 over each tool's server, name, description and parameters, and a query
in Chinese, Japanese or Korean matches tools described in that language. Coffer's own
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

## coffer\_\_ask {#coffer-ask}

Asks the owner a question in the middle of a task and waits. The turn pauses; the
question shows on the [Conversations](/guides/chat) page (and as a card in the chat, for a
conversation a [channel](/guides/channels) drives); the call returns when the owner answers
in either place, when they stop the task, or after 24 hours. It takes the shape of Claude
Code's own `AskUserQuestion`, which Coffer turns into the same question inside a Coffer
conversation.

It is **turn-scoped**: Coffer starts every agent process it runs a turn on with a random
`COFFER_TURN_TOKEN`; the shim sends it as the `X-Coffer-Turn` header, and the gateway lists
`coffer__ask` only in a session whose header names a turn that is running now. An agent
started in a terminal never sees it, and a direct call there is answered "coffer__ask works
only inside a Coffer conversation" (`isError: true`). The tool is not named in the
handshake instructions or on the built-in server's page for that reason. The `coffer` entry
Coffer writes into Codex's `config.toml` passes the variable through (`env_vars`) and
allows a tool call to run for a day (`tool_timeout_sec = 86400`).

### Input

| Property | Type | Required | Description |
| --- | --- | --- | --- |
| `context` | string | no | Markdown shown above the questions: a summary, a diff, a path. |
| `questions` | array | yes | One to four questions. |

Each question:

| Property | Type | Required | Description |
| --- | --- | --- | --- |
| `header` | string | yes | A short label. |
| `question` | string | yes | The question. |
| `options` | array | yes | Two to four options, each `{label, description?}`. Labels differ within a question. |
| `multi_select` | boolean | no | Let the owner pick several options. Default `false`. |

The owner can always type their own answer instead of choosing an option.

### Result

```json
{
  "answered": true,
  "answers": [
    { "header": "Apply", "question": "Apply this change to staging?", "selected": ["Yes"], "text": null }
  ]
}
```

`selected` holds the chosen labels and `text` the owner's own words (either may be empty,
not both). When no answer came (the owner stopped the task, or 24 hours passed) the result
is `{"answered": false, "message": "…"}`. A malformed ask fails with `isError: true` and a
message saying what to fix.

## coffer\_\_channel\_read\_thread {#coffer-channel-read-thread}

Reads a chat thread's messages page by page, newest page first. A thread turn on a
[channel](/guides/channels#groups-and-threads) carries only the thread's latest messages (or
only what is new since the conversation's previous turn there); when it leaves older ones
out, its context ends with a note naming this tool and the `before` to pass. The agent copies
the other arguments from the turn's `[Message origin]` block.

It reads only through a channel running on this machine, only a thread of a chat that channel
has paired (your direct chat with the bot, or a group you have addressed the bot in), and never
a chat's main history. Images and files on the returned messages are downloaded with the bot's
credentials, and the result gives their local paths. On Telegram, which has no history API,
the call fails saying so. Like `coffer__ask` it is **turn-scoped**: listed and served only in a
session whose `X-Coffer-Turn` header names a live turn, so an agent started in a terminal never
sees it, and the handshake instructions do not name it. The channel note of a turn on a
platform that can read threads tells the agent about it.

### Input {#input-2}

| Property | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `channel` | string | yes | | The channel's name (the origin block's `channel:` line), or its uid. |
| `chat_id` | string | yes | | The chat id from the origin block. |
| `chat_kind` | string | yes | | `direct` or `group`, from the origin block. |
| `thread_id` | string | yes | | The thread id from the origin block. |
| `before` | string | no | | A message id: return the messages older than it. Omit for the newest page. |
| `limit` | integer | no | `20` | Messages per page, 1–100 (a larger value is read as 100). |

### Result {#result-2}

```json
{
  "messages": [
    {
      "message_id": "m-5",
      "sender": "alice@example.com",
      "sent_at": "2026-10-01T08:05:00+00:00",
      "from_bot": false,
      "text": "the deploy is red again",
      "files": [{ "path": "/Users/you/.coffer/tmp/seatalk-media/3f…a1.png", "mime": "image/png", "filename": "chart.png" }]
    }
  ],
  "has_more": true,
  "next_before": "m-5"
}
```

`messages` is the page, oldest first. Pass `next_before` as `before` to read the page before
it; it is `null` when `has_more` is `false`. When the platform cannot return part of the
thread (SeaTalk returns only the last 7 days of replies), the result also carries a `note`
saying so. A channel that is not running, a chat the channel has not paired, a missing
`thread_id`, a `before` that is not in the thread and a read the platform refused each fail
with `isError: true` and a message saying which.

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
name above and agents' permission rules and skills quote those names. A server has no
separate display title; to use a different name, remove the server and register it again. A server's name is at most 24 characters. See
[MCP servers](/guides/mcp-servers).

### Client-visible name length

Clients add their own prefix, so an agent sees `mcp__coffer__<server>__<tool>`. Model
provider APIs refuse tool names longer than 64 characters, and Cursor drops tools longer
than 60. Coffer records that length for every discovered capability as
`client_name_length`, and the server's **Tools** tab
flags each tool above 64. `mcp__coffer__` (13) plus a 24-character server name plus `__`
(2) leaves 25 characters for the upstream tool's own name.

A call is refused, with JSON-RPC error code `-32000` and a message naming the reason, when:

- the capability is switched off on its server (the **Tools** tab of the server's page
  under **MCP servers**), or
- the server's [reach](/architecture/resource-framework#reach) does not include the agent
  that opened the session.

A method Coffer does not answer is `-32601`. Params a method cannot use, or a tool name
no server offers (no `<server>__` prefix, or no such server), are `-32602`. A JSON-RPC
error the upstream answered keeps its code, with Coffer's own message. Other failures
inside Coffer are JSON-RPC error `-32603`. A failing upstream tool returns its own
`isError: true` result unchanged.

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
agent's system prompt, is at most 800 characters. It reads (the memory root is
`~/.coffer/derived/memory`, outside the vault, here `/Users/you/.coffer/derived/memory`):

```text
Coffer is this machine's local vault: it aggregates the user's MCP servers behind one
endpoint, holds what this developer wrote down, and adds its own tool:
coffer__search_tools (describe an upstream tool you need; results are callable by name).
Its knowledge is markdown you read with your own file tools. Its
memory notes are Markdown under /Users/you/.coffer/derived/memory/*/notes/; grep them with your
own tools. Its own logs: coffer log audit|mcp|daemon (files: coffer path logs). The
coffer-guide skill is the manual: load it for the catalogue, with paths, before asking
the developer something they may have written down.
```

(Line breaks added here; the text is one paragraph.) When a memory root is too long for
the 800-character cap, the sentence is shortened to fit. When tiering hid tools in this session's last `tools/list`, one sentence is
appended:

```text
Your tool list is a budgeted slice: 88 more upstream tools are unlisted, all callable.
```

## Knowledge, memory and logs without a tool {#memory-and-logs-without-a-tool}

Coffer has no tool for knowledge, memory notes or its own records, because an agent can
already do all of them with what it has. To add knowledge, write a Markdown document straight
into a collection, as the `coffer-guide` skill describes; a file left in a collection's `.inbox/`
folder is adopted by Coffer's sweep, which fills in any missing frontmatter and promotes it to a
document. To change a document or a memory note, edit the file in place.

| To find | Do this |
| --- | --- |
| A knowledge document | Read the file under the collection folders the `coffer-guide` skill lists. |
| A memory note | Grep the memory root the handshake, the session-start delivery and the `coffer-guide` skill name (every partition's notes are `<root>/<partition>/notes/*.md`), then read the file. |
| What changed in Coffer (registrations, deletions, secret reads, config writes) | `coffer log audit --since 1h` |
| Which MCP calls failed | `coffer log mcp --status error --since 1h`, or `--server <name>` for one server |
| What the daemon logged, including tracebacks | `coffer log daemon --errors --since 1h`, or grep the file `coffer path logs` names |

Every `coffer log` reader takes `--json` for scripts. See
[Activity and audit](/guides/activity), [Knowledge](/guides/knowledge) and [Memory](/guides/memory).

## Related

- [Connect a client](/guides/connect-a-client) — install Coffer's MCP entry into an agent.
- [MCP servers](/guides/mcp-servers) — register the upstream servers these names come from.
- [MCP gateway](/architecture/mcp-gateway) — sessions, the shim, discovery and tiering in depth.
- [mcp-gateway spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/mcp-gateway/spec.md)
