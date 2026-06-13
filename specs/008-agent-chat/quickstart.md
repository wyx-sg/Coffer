# Quickstart — Coffer Agent Chat

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

The Chat page lets you talk to **Coffer Assistant** — Coffer's built-in agent.
The agent can use everything in your vault: your MCP server tools, your memory
stores, your knowledge bases, and your skills.

## 1. Configure a model

The built-in agent needs an LLM. Open **Settings → Models** and add one:

| Provider | What you supply |
|---|---|
| Anthropic | model id (e.g. `claude-sonnet-4-6`) + API-key credential |
| OpenAI | model id (e.g. `gpt-4o`) + API-key credential |
| Ollama (local) | model id (e.g. `llama3.1`) + base URL (e.g. `http://localhost:11434`) |

The first model you add becomes the default. A cloud model references its API
key by a credential reference; store the key itself first, then register the
model that points at it. From the command line:

```bash
# 1. Store the API key in the encrypted credential store under a reference name.
coffer credentials set anthropic-api-key     # reads the secret from stdin
# 2. Register a model that resolves its credential from that reference.
coffer model add --name "Sonnet" --provider anthropic \
  --model claude-sonnet-4-6 --credential-ref anthropic-api-key
coffer model list --json
```

API keys are stored as ciphertext in Coffer's encrypted credential store, with
only the credential reference in the model config — the plaintext key never
touches the database.

## 2. Start chatting

Open the **Chat** page (top of the sidebar). Click **New conversation**, pick an
agent in the dialog — Coffer ships **Coffer Assistant**, its built-in agent —
and confirm. Type a message, and the agent replies — streamed token by token.

Ask it something that needs your vault, for example:

> What do my memory notes say about OAuth?

The agent calls the matching tool (`coffer__recall`, `coffer__search_knowledge`,
`coffer__load_skill`, or any of your MCP server tools). Each call shows up in the
thread as an inline card you can expand to see the inputs and result.

## 3. Manage conversations

The conversation history is the left column of the Chat page (collapsible).
Create new conversations, switch between them, rename, or delete. Everything is
stored locally in SQLite and survives a restart.

## 4. Switch models per conversation

If you have more than one model configured, the model selector in the
conversation's top bar changes which model that conversation uses. The choice
applies to the next turn onward; each reply records the model that produced it.

## 5. Chat from the command line

```bash
coffer chat -m "say hello"        # one turn, prints the reply
coffer chat                       # interactive multi-turn session
```

CLI conversations are the same conversations the desktop app shows.

## Conversation retention (and an upgrade note)

Conversations follow a two-stage lifecycle, both windows configurable under
**Settings → Data**:

1. **Auto-archive idle chats** — a conversation with no new message for the
   auto-archive window (default **7 days**) is archived (it leaves the active
   list but is not destroyed).
2. **Delete archived chats** — an archived conversation (and its messages) is
   deleted the configured number of days **after it was archived** (default
   **30 days**).

Either window can be set to *off* to disable that stage. Active conversations
(never archived) are never deleted by the delete stage.

> **Upgrade note (behaviour change).** Earlier builds deleted conversations by
> *last activity* (a single stage). The lifecycle is now the two-stage model
> above: the delete window is measured from *archival*, not last activity, and
> the separate auto-archive window was added. On upgrade, a legacy single-stage
> retention setting is reset to the new defaults (archive 7 days + delete 30
> days); a setting you had **disabled** stays disabled. If you previously
> customised conversation retention, re-check **Settings → Data** after
> upgrading. This is safe: the new delete stage only ever removes *archived*
> threads, so no active conversation is deleted by the change.

## What happens behind the scenes

- Conversations and messages are rows in Coffer's SQLite database — not
  Resources. They are surface artefacts, not configured vault assets.
- The built-in agent runs an in-process LangGraph loop and reaches your tools
  through Coffer's own MCP gateway, so every tool call goes through the gateway's
  capability gating and invocation log.
- Token usage is recorded on every assistant message and shown beneath the
  reply. Each completed **turn** is recorded in `coffer audit list` with actor
  `agent`; the individual **tool invocations** are recorded in the MCP gateway's
  invocation log (under the agent's gateway session), not the audit log.

## Troubleshooting

**"No model configured"** — the Chat page shows this until you add a model in
Settings → Models. Add one and the chat input unlocks.

**A turn fails with a provider error** — check the model's credential and, for
Ollama, that the base URL is reachable. The conversation stays usable; just send
the message again.

**The agent didn't use a tool you expected** — confirm the relevant MCP server,
memory store, or knowledge base is enabled; disabled capabilities are not
offered to the agent.
