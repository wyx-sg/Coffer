## Context

A Coffer turn runs an agent subprocess (Claude Code through the Agent SDK with
`permission_mode="bypassPermissions"`; Codex through `codex app-server`). The
agent reaches Coffer's tools through the stdio shim, which proxies MCP calls to
the daemon's `/mcp` endpoint. A turn already carries a `conversation_id` and a
`turn_id` (spec resource-framework "Correlate the audit log, the MCP invocation
log and the daemon log by one trace id"), but an MCP call does not say which turn
it came from.

## Goals / Non-Goals

**Goals:** one question model for `coffer__ask` and `AskUserQuestion`; the turn
really pauses; one answer wins wherever it is given; options like Claude Code's
(several options with descriptions, multi-select, free text); the list and the
sidebar know a conversation is waiting.

**Non-Goals:** Overview listing waiting conversations (the Shell canvas decides);
asking outside a turn Coffer runs; tool-permission approvals (Coffer still runs
agents with full permissions).

## Decisions

### 1. Which turn an ask belongs to: a turn token in the agent's environment
Coffer starts each turn's agent process with `COFFER_TURN_TOKEN=<random 128-bit>`
in its environment and registers the token → (conversation, turn, reply message)
for the turn's lifetime. The shim reads the variable at start and sends it as
`X-Coffer-Turn` on every request to `/mcp`. The gateway lists `coffer__ask` only
in a session whose header names a live turn, and resolves the call to that turn.
Claude Code passes its environment to stdio MCP servers. Codex passes only a
default set, so the Codex entry Coffer writes for the `coffer` server adds
`env_vars = ["COFFER_TURN_TOKEN"]`.
*Alternatives:* matching the MCP session to the turn by timing (racy with two
turns on one agent); a per-turn MCP server URL (needs per-turn config files).

### 2. The call blocks; timeouts are lifted for it
`coffer__ask` returns only when answered, cancelled (Stop, the turn ends, the
daemon shuts down) or after 24 hours ("No answer"). Claude Code's MCP tool
timeout is far above that by default. Codex's default `tool_timeout_sec` is 60, so
the `coffer` server entry Coffer writes sets it to 86 400. Every other `coffer__`
tool returns quickly, so the longer limit costs nothing.

### 3. `AskUserQuestion` is intercepted by a PreToolUse hook, not `can_use_tool`
The owner asked for `can_use_tool`. In the SDK this repo pins (0.2.152) that
callback is never consulted under `bypassPermissions`: the SDK itself warns
"can_use_tool will not be invoked … auto-approves every tool call … use a
PreToolUse hook instead". Coffer keeps bypass (it does not gate tool calls), so
the adapter registers a `PreToolUse` hook matching `AskUserQuestion` with a 24 h
timeout. The hook raises the question and, once answered, returns
`permissionDecision: "allow"` with `updatedInput` carrying the answers in the
tool's `answers` field — the same result a `can_use_tool` callback would return.
A cancelled question returns `deny` with "The owner did not answer." The first
implementation task verifies this against the bundled CLI; if `answers` in
`updatedInput` is not honoured, the hook denies with the answers in the message.

### 4. One question model
`coffer__ask` input mirrors `AskUserQuestion`:
`{context?: markdown, questions: [{header, question, options: [{label, description?}] (2–4), multi_select}] (1–4)}`.
Stored as a content block of type `question` in the reply that asked, so it
renders in place and survives reload: `{question_id, context, questions, status:
pending|answered|cancelled, answers: [{header, selected: [labels], text?}],
answered_via: web|<channel uid>, answered_by, answered_at}`. The `tool_use` of
`coffer__ask` / `AskUserQuestion` is not rendered as a tool card. Turn events
`question_asked` and `question_closed` carry the block.

### 5. Answers: first one wins
`POST /chat/conversations/{id}/questions/{qid}/answer {answers}` and the channel
paths go through one application function that atomically moves pending →
answered; a second answer gets `QUESTION_CLOSED` and changes nothing. Free text is
an answer: the web reply box and a channel text message in that chat, while a
question is pending, answer it — the text is the "Other" answer of the first
unanswered question (several questions in one ask are answered one card at a
time, in order). A tap in a group is owner-gated like every card tap.

### 6. Rendering in chat apps
One card per question in turn order. SeaTalk: card body = context (a diff as a
code block) + "❓ question" + options with descriptions as a list when any has a
description; buttons one per option (≤4, equal style); multi-select buttons
toggle a ✓ and a **Submit** button sends; footer "Or reply with your answer.".
Telegram: the same as a message with an inline keyboard. When answered anywhere,
every card of the question is rewritten to "✓ Answered: <labels> · HH:MM"
("✓ Answered in Coffer: …" for a web answer); a platform that cannot edit sends
that line as a reply. The long-task ping reads "❓ Needs you · 4m — <question>".

### 7. Waiting is visible
`ConversationOut.needs_you: bool` (a pending question exists) drives the list's
warning "Needs you" status; `GET /chat/conversations/needs-you-count` drives the
sidebar badge (refetched on `question_*` events). The reply header reads
"Waiting for you".

## Risks / Trade-offs

- [Codex env passing] → covered by `env_vars`; integration test with a fake shim env.
- [Hook result shape changes in a CLI update] → the verification task pins it with a recorded fixture test; the deny fallback still delivers the answer.
- [An agent asks outside a Coffer turn] → the tool is not listed there; a direct call answers "only inside a Coffer conversation".
- [Stop while waiting] → the question is cancelled, cards are rewritten "Stopped", the tool returns "The owner stopped the task."

## Migration Plan

Remove `needs_you.py`, its prompt note and its tests; migration adds nothing for
old replies (a historical `NEEDS YOU:` line stays as text). The Codex config
rewrite happens on the next agent config sync.
