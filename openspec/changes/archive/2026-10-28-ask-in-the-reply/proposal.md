## Why

A SeaTalk bot asked the owner which market a request was for, got the answer,
and asked again. Coffer kills a turn's Codex app-server before the turn runner
closes its questions with `keep_open`, so the open `coffer__ask` was cancelled
and the owner's answer started a fresh turn the agent could not connect to its
question. The owner's view: a person in chat just asks, all at once, and the
reply is the answer; one card per question is slower and SeaTalk cards cannot
hold the options anyway. The options are argued in ADR
`ask-in-the-reply-not-in-a-card`.

## What Changes

- **No question mechanism.** `coffer__ask`, pending questions, the
  `AskUserQuestion` interception, question cards, the question events and the
  **Needs you** status are removed everywhere (channels, Conversations page,
  Agent › Sessions, APIs).
- **The agent asks in its reply**, every question in one message, and ends the
  turn; the owner's next message is the answer and starts the next turn. The
  channel note says so.
- **Claude Code runs without `AskUserQuestion`** (`disallowed_tools`) in every
  Coffer turn.
- **A more human default reply style**: nothing repeated back, no narrated
  steps or caveats, everything needed asked at once.
- The turn token stays, scoping `coffer__channel_read_thread`; old card taps
  are ignored. The busy dialog offers **Continue in <platform>**.

## Impact

- Removed: `application/mcp/gateway_ask.py`, `application/chat/questions.py`,
  `question_listeners.py`, `question_agents.py`, `domain/chat/question.py`,
  `infrastructure/chat/claude_sdk_questions.py`,
  `application/channel/question_flow.py`, `question_card.py`.
- Renamed: `turn_ask.py` → `turn_scope.py`, `question_turns.py` →
  `turn_tokens.py`.
- `turn_runner.py`, `claude_sdk_agent.py`, `channel_prompt.py`, channel inbound
  and render, session listing schemas; frontend session rows and busy dialog.
- Specs `chat`, `channels`, `mcp-gateway`, `agent-registry`, edited directly
  (`skip_specs: true`). docs-site (en, zh); Run design canvas.
