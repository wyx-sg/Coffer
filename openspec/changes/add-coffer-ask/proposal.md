## Why

When an agent needs the owner to decide something mid-task, Coffer only has a
soft convention: the agent may end its reply on a `NEEDS YOU: <question> (a / b)`
line, which a channel turns into Yes / No buttons and the web page shows as plain
text. The turn has already ended by then, a tap is sent back as the owner's own
message, nothing tells the Conversations page that a conversation is waiting, and
an agent that asks through Claude Code's own `AskUserQuestion` dialog gets no
answer at all, because nothing in a Coffer conversation can show that dialog.

The Run canvas (3.1.10–11, 3.3.16–17) replaces this with a real question: the
agent asks, its turn pauses, the owner answers in Coffer or in the chat, and the
answer goes straight back to the agent.

## What Changes

- **New built-in MCP tool `coffer__ask`**, offered only inside a turn Coffer runs
  (a Coffer conversation or a channel conversation). Its input has the shape of
  Claude Code's `AskUserQuestion`: one to four questions, each with a short
  header, the question, two to four options (label + optional description) and
  `multi_select`; plus an optional `context` (markdown: a summary, a diff, a
  path) shown above the question. The call blocks until every question is
  answered, the turn is stopped, or 24 hours pass; it returns the answers.
- **Claude Code's `AskUserQuestion` becomes the same question.** In a Coffer
  turn the Claude Code adapter intercepts the tool before it runs, raises the
  same question, and hands the answers back as the tool's answers.
- **A pending question is state**: stored with the reply it belongs to
  (pending / answered / cancelled, the answer, where it was answered and when),
  streamed as turn events, and rendered in the reply.
- **Conversations page**: the reply's header reads "Waiting for you"; a question
  card sits at the end of the reply, above the reply box — context, question,
  equal option buttons (toggle buttons + Submit for multi-select), "Or reply
  with your answer."; text typed in the reply box while a question waits is the
  answer, not a queued message. Answered, the card shrinks to
  "✓ <question> · Answered: Yes · 10:16" (with "in SeaTalk" when answered there).
  The list shows a warning "Needs you" status on the conversation's row and the
  sidebar's Conversations item counts conversations waiting on you.
- **Channels**: the question goes out as one card — context, ❓ question, up to
  four equal buttons (one row each, with their descriptions in the body),
  multi-select as toggles plus Submit, and "Or reply with your answer."; the
  owner's next text message in that chat is the answer. Nothing is posted as the
  owner. Once answered anywhere the card is rewritten to
  "✓ Answered: Yes · 11:42" ("✓ Answered in Coffer: …" when answered there).
- **BREAKING (agent-facing convention)**: the `NEEDS YOU:` last-line sentinel and
  its prompt note are removed; the channel note tells the agent to call
  `coffer__ask` instead.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `mcp-gateway`: a turn-scoped built-in tool `coffer__ask`.
- `chat`: pending questions on a reply, the web question card, answering from the
  reply box, the Needs you status and sidebar count, `AskUserQuestion` interception.
- `channels`: the question card, answering by tap or text, rewriting the card when
  answered elsewhere; the `NEEDS YOU:` sentinel requirement is removed.

## Impact

- Backend: gateway built-in tools, the shim (forwards the turn token), the Claude
  Code adapter (PreToolUse hook), the Codex config Coffer writes
  (`tool_timeout_sec`, `env_vars`), chat persistence (migration), turn events,
  channel turn rendering and inbound routing, `needs_you.py` deleted.
- REST: `GET` pending questions with the conversation, `POST …/questions/{id}/answer`;
  `ConversationOut.needs_you`; a count for the sidebar.
- Frontend: question card, reply box routing, list status, sidebar badge.
- Docs: chat and channels guides, channel-commands reference, mcp-tools reference (en + zh).
