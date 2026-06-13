# Chat

Coffer's **Chat** is a streamed conversation with an AI agent that runs against your vault. Two kinds of agent answer here:

- the **built-in agent** ("Coffer Assistant") — an in-process agent that runs on an LLM you configure and reaches your MCP tools, knowledge bases, memory, and skills through Coffer's own gateway;
- **CLI agents** — your installed **Claude Code** or **Codex** binaries, driven in a working directory you pick per conversation.

::: tip Configure a model first
The built-in agent has no model of its own. Add one under **Settings → Models** (or `coffer model add`) before chatting; the first model you register becomes the default. CLI agents use their own configured model, not Coffer's.
:::

## Chat from the command line

`coffer chat` talks to the **built-in agent**:

```bash
coffer chat -m "what MCP servers and knowledge bases do I have?"   # one turn, prints the reply
coffer chat                                                        # interactive multi-turn session
coffer chat --model <model-id>                                     # pick a model for a new conversation
coffer chat -c <conversation-id>                                   # resume a conversation
```

- `coffer model add --name … --provider <anthropic|openai|ollama> --model … [--default]` registers a model; `coffer model list` / `edit` / `rm` manage them.
- CLI conversations are the same conversations the desktop and web apps show — they persist in SQLite and survive a restart.

::: tip Chatting with Claude Code / Codex
Choosing a CLI agent and its working directory happens in the app's **New conversation** dialog, not on the CLI — `coffer chat` always uses the built-in agent.
:::

## Chat in the app

The **Chat** page is the top entry in the sidebar:

1. Click **New conversation** and pick an agent. For the built-in agent, choose a model; for Claude Code / Codex, choose a **working directory**.
2. Send a message and watch the reply stream in. Tool calls appear as inline cards you can expand.
3. An agent that asks permission for a tool shows an **Allow / Deny** card; the turn pauses until you decide. (The built-in agent does not pause.)
4. **Stop** ends a turn and keeps the partial output. The composer is locked while a turn is streaming.

## Retention

Conversations follow a two-stage lifecycle, both windows configurable under **Settings → Data**: idle threads are auto-archived (default 7 days), then archived threads (and their messages) are deleted a while after archival (default 30 days). Active conversations are never deleted by the delete stage; either stage can be turned off.

[Skills →](/guide/skills)
