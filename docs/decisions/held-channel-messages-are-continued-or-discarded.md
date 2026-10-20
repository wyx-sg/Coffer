# Held Channel Messages Are Settled by Continue and Discard

**Status**: Accepted
**Date**: 2026-10-20
**Deciders**: Yuxing Wu
**Related**: [Channel `/help` Is a List to Read, and a Card Carries Only the Buttons That Act on It](channel-help-is-a-list-and-cards-carry-only-their-own-actions.md), [A Burst of Channel Messages Is One Turn, Released After a Per-Channel Quiet Window](a-burst-of-channel-messages-is-one-turn.md), spec channels "Continue or discard the messages a stop held", spec chat "Pause the pending queue on interrupt"

## Context

Messages sent while a turn runs wait in the conversation's pending queue. An
interrupt pauses that queue (spec chat "Pause the pending queue on interrupt"),
so nothing queued fires into the turn just stopped. From a chat, the only way
out was "send anything to continue": the held messages could be resumed but
never dropped. After `/new` the held queue belonged to the old conversation and
nothing in the chat could reach it again. `/status` counted held messages as
"n waiting", as if they were about to run.

The owner asked how comparable products handle queued messages, then whether
`/status` should show them. Public docs as of 2026-10:

- **Claude Code / Codex terminals**: an interrupt puts queued messages back in
  the input box to edit or delete (from using them; not found stated in docs).
- **Augment** ([message queue](https://docs.augmentcode.com/using-augment/message-queue)):
  a panel above the input: edit, delete, reorder, send now, pause and resume.
- **Happier** ([pending queue](https://docs.happier.dev/features/pending-queue)):
  edit, reorder, remove, send now; a discarded section to re-queue from.
- **OpenClaw** ([queue steering](https://docs.openclaw.ai/concepts/queue-steering.md)):
  modes for messages that arrive while busy (steer, follow up, collect,
  interrupt); a pending message can be withdrawn one by one.
- **cc-connect, claude-code-telegram**: their docs do not say.

Common ground: a stop does not run what was queued, and there is always a way to
throw it away.

## Options Considered

### Option A — Continue and Discard buttons on the stopped line and on `/status` (chosen)

When a stop holds messages, "⏸ N queued messages are on hold." carries
**Continue** (run them in order) and **Discard** (drop them). On Telegram, which
edits "Stopping…" into the stopped line, the buttons ride that message; on
SeaTalk, which cannot edit a plain message, the held line follows the reply as a
card. `/status` shows "⏸ n on hold" and the same two buttons. Sending anything
still continues them.

- Pros: both ways out are one tap where the owner already looks; it is the
  `/stop`'s own follow-up, so it obeys "each command carries only its own
  buttons"; nothing new to type or remember; works after `/new`, because the
  button names the stopped conversation.
- Cons: two more buttons and, on SeaTalk, one more message after a stop that
  held something. No way to drop one message and keep the rest.

Wins because it closes the gap with the least the owner has to learn.

### Option B — Discard on a typed command (`/stop` twice, or `/clear`)

- Pros: works on a transport without buttons.
- Cons: a tenth reserved word, or a hidden meaning for a second `/stop`; the
  owner asked for fewer, clearer commands, and both channels have buttons.

### Option C — Give the queued messages back to the owner

The terminals' way: return the text so it can be edited and resent.

- Pros: nothing is lost; the owner decides per message.
- Cons: a chat has no input box to put text into; quoting the messages back is a
  wall of text the owner must copy by hand.

### Option D — Per-message management (list, delete one, reorder)

- Pros: the panels' full control.
- Cons: a card per message or numbered commands to match; far more than a phone
  chat needs for a queue capped at ten.

### Option E — Leave it: send anything to continue

- Pros: nothing to build.
- Cons: what was queued can only ever run; after `/new` it is stranded.

## Decision

`TurnOrchestrator` gains `held(id)`, `resume_held(id)` and `drop_held(id)`. The
buttons carry `held:go:<conversation id>` and `held:drop:<conversation id>`
(`application/channel/held_queue.py`); a tap acts only on a conversation of that
chat thread's own history and with something on hold, and otherwise answers
"Nothing is on hold any more.". The stopped line names the count; `/status`
reads "⏸ n on hold" (a parallel thread "n on hold").

## Consequences

- Discarded messages never reach the agent; the queued receipt the chat already
  showed for them is not withdrawn.
- A stop in a SeaTalk group's main chat, which stops every turn in the group,
  still lists what it stopped without per-conversation buttons; `/status` there
  is a direct-chat command, so held messages in group threads are resumed by
  the next message, as before.
- The queue stays in memory: held messages still go with a daemon restart.
