# A Question Outlives the Turn That Asked It, and Its Answer Starts the Next Turn

**Status**: Accepted
**Date**: 2026-10-26
**Deciders**: Yuxing Wu
**Related**: [Held Channel Messages Are Settled by Continue and Discard](held-channel-messages-are-continued-or-discarded.md), spec chat "Pause a turn on a question for the owner", spec chat "Keep a question open past the turn that asked it", spec channels "Ask the owner in the chat and take the chat's answer back to the agent"

## Context

A question an agent asks the owner (`coffer__ask`, or Claude Code's
`AskUserQuestion`) used to live exactly as long as the turn that asked it. The
design assumed the ask blocks: Claude Code's `AskUserQuestion` does, and Coffer
gives Codex's `coffer` MCP entry a 24-hour `tool_timeout_sec` so `coffer__ask`
can block too.

On 2026-10-26 a Codex turn in a SeaTalk group asked which site six shops
belonged to and did not wait. The Codex rollout on the owner's Mac shows why:
Codex's code mode ran `tools.mcp__coffer__coffer__ask(...)` inside a background
`exec` cell (`yield_time_ms: 1000`), got "Script running" back after a second,
polled the cell with `wait` for about a minute, then wrote its final reply and
finished. The turn's end cancelled the open question, so the card read
"⏹ Stopped" three minutes after it went out, and the final reply asked the same
thing again as text. Whether an agent blocks on a tool is the agent's choice;
Coffer cannot force it.

The owner's ask: when the agent asks, stop there, wait for the answer, and go
on only after it.

How comparable products handle it (2026-10):

- **Claude Code `AskUserQuestion`**: the tool call blocks until the user picks;
  the process stays up.
- **Codex `request_user_input`**: the app-server sends the client a request and
  the turn blocks on it.
- **LangGraph `interrupt()`**: the run pauses at the question and checkpoints;
  the process may exit. The answer resumes it from the checkpoint
  (`Command(resume=...)`), across restarts.
- **Devin, OpenHands, Claude in Slack**: the agent asks and ends its turn; the
  user's next message is the answer and starts a new turn, carried by the
  session history.

Common ground: asking means stopping, and the answer is what lets the work go
on. The two shapes are "the turn blocks" and "the turn ends; the answer starts
the next one". The second survives an agent that does not block.

## Options Considered

### Option A — A question outlives a turn that finished; its answer starts the next turn (chosen)

When a turn finishes on its own with a question still pending, the question
stays pending: the conversation still needs the owner, and the card keeps its
buttons. Whatever still awaits the ask is told the turn ended and the answer
comes as the next message. Once the owner answers (tap or text), the card is
rewritten as usual and the answer goes to the agent as the conversation's next
message: the questions with their answers. That message starts a turn like any
other. A stopped, failed or shut-down turn still cancels its question; a new
question in the conversation cancels one an earlier turn left open; one left
open is given up on after 24 hours. The channel note also tells the agent to
wait for the answer or end its turn silently.

- Good: works whatever the agent does with the tool call. An agent that blocks
  (Claude Code) is unchanged and keeps going in the same turn; one that does not
  (Codex code mode) gets the answer in its next turn, with its session history.
- Good: no agent process is held open for hours on an unanswered question.
- Cost: the question now has two lives (inside a turn, after one), and the
  channel renders a late answer itself because no turn renderer is there.
- Cost: an open question is in memory only, like every question: a daemon
  restart drops it and its card keeps buttons that no longer answer.

### Option B — Coffer interrupts the turn as soon as a question is asked

The card goes out and Coffer stops the turn at once; the answer starts the next
turn. Closest to "stop there" taken literally, and one behaviour for every
agent.

- Lost: Claude Code, which blocks properly and could carry on in the same turn,
  would be cut off mid-tool and resume from history, which is worse than today.
  An agent may be running another tool in parallel when it asks; interrupting
  leaves that half done.

### Option C — Only tell the agent, in the channel note, to block on the answer

The smallest change. It does not reach the cause: Codex's code mode decides how
long to wait on a background cell, and a prompt cannot guarantee it waits a day.
The failure would return on the next long question.

### Option D — Persist open questions so they survive a restart

LangGraph's checkpoint shape. Coffer stores no question and no reply text by
design (spec chat "Pause a turn on a question for the owner"), and a restart
already ends every turn. Not worth a store for the rare restart in the middle of
an unanswered question.

## Decision

Option A, with the note from Option C as a hint on top. The turn runner closes a
finished turn's questions with `keep_open`; the channel keeps a finished turn's
cards and, when a late answer completes a question, sends its follow-up as the
owner's next message in that chat or thread.

## Consequences

- An agent that ends its turn after asking gets the answer as its next message
  ("You asked me this earlier and your turn ended before I answered…"), not as
  a tool result.
- A conversation keeps "Needs you" after its turn ends, until the question is
  answered, superseded or 24 hours pass.
- A card whose question was lost to a restart keeps its buttons; a tap on it
  does nothing.
