# An Agent Asks the Owner in Its Reply, Not in a Question Card

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Yuxing Wu
**Related**: [A Channel's System Prompt Is a Fixed Channel Note Plus a Reply Style the Owner Can Rewrite](channel-prompt-fixed-note-and-editable-style.md), [Held Channel Messages Are Settled by Continue and Discard](held-channel-messages-are-continued-or-discarded.md), spec chat "Ask the owner in the reply, not in a dialog", spec mcp-gateway "Offer turn-scoped tools only inside a Coffer turn"

## Context

Until this decision an agent asked the owner through a question mechanism of
Coffer's own: the built-in MCP tool `coffer__ask` (and Claude Code's
`AskUserQuestion`, which Coffer intercepted and turned into the same question).
The turn paused on a pending question; a channel showed it as a card with up to
four buttons per question, one question at a time; the Conversations page
marked the row **Needs you**. A question that outlived its turn (an agent that
did not block on the tool) was kept open, and its answer started the next turn.

On 2026-10-28 a SeaTalk direct chat showed the bot asking which market a
request was for, the owner answering, and the bot asking the same thing again.
The cause was in the question mechanism itself. Coffer runs one Codex
app-server per turn and kills it when the turn ends; the adapter killed the
process before the turn runner closed the turn's questions with `keep_open`, so
the open question was cancelled as part of the shutdown. The owner's typed
answer then arrived as an ordinary message, started a fresh turn, and the
agent, which had never received a tool result, asked again. The "keep the
question open past its turn" design (2026-10-26) had never worked for Codex.

The owner's view, asked to fix it: a person in a chat does not send a form.
They ask, all at once, and wait for the reply. One card per question, tapped
one at a time, is slower than typing one answer, and SeaTalk cards are limited
to three rows of three buttons, so options do not fit anyway.

How comparable products ask (2026-10):

- **ChatGPT, Claude.ai, Gemini**: the assistant asks in its message and stops;
  the user's next message is the answer. No question widget in chat.
- **Claude in Slack, Devin, OpenHands**: the agent asks in a thread reply and
  ends its turn; the next message continues the session from its history.
- **OpenClaw and other IM agent bridges** (see
  [IM agent bridges](../research/im-agent-bridges.md)): plain-text questions in
  the chat; buttons only for the bridge's own commands.
- **Claude Code `AskUserQuestion`**: a blocking multiple-choice dialog in the
  CLI. It assumes a person at the terminal, which a Coffer turn does not have.
- **Codex `request_user_input`**: the app-server asks the client and the turn
  blocks; the same assumption.
- **LangGraph `interrupt()`**: the run checkpoints at the question and resumes
  from it with the answer; it needs a store for paused runs.

Common ground: chat products ask in text and treat the next message as the
answer. Blocking dialogs exist only where a person is at the client.

## Options Considered

### Option A — Ask in the reply; the answer is the next message (chosen)

There is no question mechanism. The channel note tells the agent: to get
something from the person, ask in the reply, all questions in one message, and
end the turn; the answer comes next. The default reply style says the same in
its own words ("ask for all of it at once, then stop"). Claude Code runs with
`AskUserQuestion` in `disallowed_tools`, so it cannot open a dialog nobody will
see. `coffer__ask`, pending questions, the question card, the **Needs you**
status and the question events are removed.

- Good: nothing to lose between turns. The answer is a normal message carried
  by the agent's own session history, the shape every agent already handles,
  whether it blocks on tools or not.
- Good: several questions are answered in one reply, in the person's own words;
  a partial answer is followed up like in any conversation.
- Good: removes a whole subsystem (an MCP tool, an interception path, a
  pending-question store, card rendering, a status word) and its failure modes.
- Cost: no buttons for a quick choice; "yes" is typed. In a group the owner
  must @mention the bot, as for any message to it.
- Cost: whether the agent stops after asking depends on the prompt. An agent
  that asks and carries on anyway is answered by the owner's next message all
  the same, which is no worse than a card it would not have waited for.

### Option B — Keep cards and fix the shutdown order

Close the turn's questions with `keep_open` before the adapter kills the Codex
app-server, so the open question survives and its answer starts the next turn
(the 2026-10-26 design, repaired).

- Good: keeps buttons, and fixes the incident.
- Lost: keeps every other cost (one card per question, SeaTalk's 3×3 button
  limit, two lives for a question, in-memory state a restart drops, cards whose
  buttons stop working), and the owner's objection is to the cards themselves.

### Option C — Cards answered only by a reply to the card

Keep the card as a display of the questions, but take only a text reply to it
as the answer; no buttons.

- Lost: a card that is just text is a reply with extra machinery. It still
  needs a pending question to match the reply to, and the same shutdown race.

### Option D — One card listing all questions

One card per ask instead of one per question, each question with its own
buttons and a Submit.

- Lost: SeaTalk fits three rows of three buttons, so two questions with options
  already overflow; the pending-question state and its race remain.

### Option E — Persist questions across turns and restarts

LangGraph's checkpoint shape: store each open question and resume the agent
with its answer.

- Lost: Coffer stores no conversation text by design, and the store would serve
  a mechanism Option A makes unnecessary.

## Decision

Option A. An agent asks the owner in its reply, every question in one message,
and ends its turn; the owner's next message is the answer and starts the next
turn. Coffer has no ask tool, no pending question and no question card. Claude
Code runs every Coffer turn with `AskUserQuestion` disallowed. A future change
must not reintroduce a question that waits across a turn boundary in Coffer's
memory.

## Consequences

- The turn token (`COFFER_TURN_TOKEN` / `X-Coffer-Turn`) stays: it still scopes
  `coffer__channel_read_thread` to sessions inside a Coffer turn.
- A tap on a question card sent before the upgrade does nothing (its callback
  prefix is ignored).
- The Conversations page and Agent › Sessions show only **Running**; the busy
  dialog offers **Continue in <platform>** or stopping the turn.
- Enforced in `coffer/domain/chat/channel_prompt.py` (note and default style)
  and `coffer/infrastructure/chat/claude_sdk_agent.py` (`disallowed_tools`).
