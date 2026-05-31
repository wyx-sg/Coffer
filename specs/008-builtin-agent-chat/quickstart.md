# Quickstart — Coffer Built-in Agent & Chat

Chat with Coffer's own built-in agent, or with a Coffer-managed external agent
(`claude_code` / `codex`), from the desktop app or the command line. The
built-in agent can reach everything the vault manages through Coffer's MCP
gateway.

## Prerequisites

- Coffer's daemon is running (start the desktop app or `coffer daemon`).
- A built-in agent named `coffer` is seeded automatically on first startup.
- For the **built-in** agent: an LLM provider key. The seeded default model is
  `anthropic:claude-sonnet-4-6`, so set an Anthropic key — store it in the
  keychain and point the agent's `credential_ref` at it, or export
  `ANTHROPIC_API_KEY` in the daemon's environment. Local models work with no
  key (e.g. switch the model to `ollama:llama3`).
- For an **external** agent: register `claude_code` and/or `codex` (spec 004),
  and have the agent's CLI (`claude` / `codex`) installed and on `PATH`.

## Configure the built-in agent's model and key

The built-in agent is an ordinary Resource of kind `builtin_agent`, edited
through the normal config-edit path. Its config fields:

| Field            | Example                       | Meaning                                             |
| ---------------- | ----------------------------- | --------------------------------------------------- |
| `model`          | `anthropic:claude-sonnet-4-6` | provider-qualified model id                         |
| `system_prompt`  | `"You are Coffer's agent…"`   | optional steering prompt                            |
| `temperature`    | `0.7`                         | optional, `0.0`–`2.0`                               |
| `max_tokens`     | `2048`                        | optional, `> 0`                                     |
| `credential_ref` | `anthropic-key`               | keychain ref for the provider key (cloud providers) |
| `use_gateway`    | `true`                        | give the agent Coffer's MCP gateway tools           |
| `confirm_tools`  | `["*delete*", "*write*"]`     | tool-name globs that pause for human confirmation   |

To use a local provider instead, set `model` to e.g. `ollama:llama3` and clear
`credential_ref` — no key needed. If a cloud provider has neither a stored
credential nor an environment key, the next `send` returns `503
LLM_NOT_CONFIGURED` (read paths keep working).

## Chat from the desktop app

1. Open **Chat**.
2. Click **New** and pick a target from the picker — the built-in `coffer` agent
   or any enabled chat-capable managed agent (`claude_code` / `codex`).
3. Type a message and send. The reply streams in token-by-token. Tool calls
   show as rows; a confirmation-gated tool shows a card with the tool name and
   arguments.
4. Use **Stop** to halt a streaming reply (the partial reply is kept, marked
   canceled).
5. Rename, archive, restore, or delete the conversation from the list.

## Chat from the command line

```bash
# Start a conversation (defaults to the built-in agent)
coffer chat new
# => <conversation-id>

# …or target a managed agent
coffer chat new --agent agent:claude-code

# Send a message and watch it stream in the terminal
coffer chat send <conversation-id> "search my memory for branch naming, then list my MCP servers"

# Print the conversation + message history (JSON for piping)
coffer chat show <conversation-id> --json

# List conversations
coffer chat list
coffer chat list --json

# Rename / archive / restore / delete
coffer chat rename <conversation-id> "MCP audit"
coffer chat archive <conversation-id>
coffer chat restore <conversation-id>
coffer chat rm <conversation-id>            # add --force to skip the prompt
```

The target ref is `builtin_agent:<name>` or `agent:<name>`; `coffer chat new`
defaults to `builtin_agent:coffer`.

## Use confirmations

When the built-in agent proposes a tool whose name matches the agent's
`confirm_tools` policy (the seeded default gates `*delete*`, `*clear*`,
`*remove*`, `*write*`), the turn pauses and emits a `confirmation` event naming
the tool and its arguments.

In the desktop app, click **Approve** or **Deny** on the confirmation card.

From the CLI, the `send` stream prints the request id; resolve it with:

```bash
coffer chat confirm <conversation-id> <request-id> --approve
coffer chat confirm <conversation-id> <request-id> --deny
```

Approving runs the tool and resumes the turn; denying skips it and tells the
agent the call was declined. A confirmation that is never answered does not
corrupt the conversation — the turn simply ends with the tool declined.

## Stop an in-flight turn

```bash
coffer chat stop <conversation-id>
```

Streaming halts, the assistant message is marked `canceled` with its partial
content retained, and any spawned subprocess (external agents) is terminated.

## REST equivalents

All operations are available over the loopback REST API under
`/api/v1/conversations` (see [contracts/api.openapi.yaml](./contracts/api.openapi.yaml)).
`POST /{id}/messages` returns a `text/event-stream` of SSE events:

```bash
curl -N http://127.0.0.1:8000/api/v1/conversations/<id>/messages \
  -H "X-Coffer-Token: $COFFER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}'
```

```
data: {"type":"text_delta","text":"Hi"}
data: {"type":"tool_call","id":"…","tool":"coffer__memory_search","args":{…}}
data: {"type":"tool_result","id":"…","tool":"coffer__memory_search","ok":true,"summary":"…"}
data: {"type":"done"}
```

Event types: `text_delta`, `tool_call`, `tool_result`, `confirmation`, `error`,
`done`.

## Troubleshooting

**`503 LLM_NOT_CONFIGURED` on send** — the built-in agent's provider has no
usable key. Set `credential_ref` to a keychain entry holding the provider key,
export the provider's env key (e.g. `ANTHROPIC_API_KEY`), or switch `model` to a
local provider that needs no key.

**External agent "binary not found on PATH"** — install the agent's CLI
(`claude` / `codex`) and ensure it is on the daemon's `PATH`, or set
`COFFER_CHAT_BIN_CLAUDE_CODE` / `COFFER_CHAT_BIN_CODEX` to its absolute path.

**`409 CONVERSATION_BUSY`** — a turn is already streaming for that conversation.
Wait for it to finish (or `coffer chat stop`) before sending again.

**`409 CANNOT_DELETE_LAST_BUILTIN_AGENT`** — Coffer keeps at least one built-in
agent so the chat surface always has a target. Add another `builtin_agent`
before deleting this one (or just edit it instead).
