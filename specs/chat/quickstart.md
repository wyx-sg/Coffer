# Quickstart: Chat

> **This one is driven from the browser.** Every other spec's quickstart is a
> list of `coffer` commands; chat ships no `chat` command group, so the page is
> the surface. The spec's `## Assumptions` records that as a known gap. The
> `curl` lines below are the same operations against the daemon, for scripting
> and for checking behaviour without a browser — they are not a CLI.

## Before you start

- The daemon is running (`coffer daemon start`) and you have its token.
- At least one managed agent is installed and on the daemon's PATH — Claude Code
  or Codex. With none, the page says so and offers no composer.
- A Coffer LLM connection is **optional**. With none, turns run on the agent's
  own model and login.

## Send your first turn

1. Open Coffer and go to **Chat**. You land on the draft surface: no
   conversation exists yet.
2. Pick the agent at the top of the draft. Pick a model if you want one — the
   dropdown lists what that agent can be put on, and an empty value means the
   agent's own default. If the model reports reasoning levels, a second control
   appears beside it; if it does not, nothing appears.
3. Type a message and send. **That send is what creates the conversation** — it
   appears in the left column, named after what you typed, and the reply starts
   streaming.
4. Watch the reply grow. Tool calls render as their own cards in the order the
   agent emitted them; a card with no result yet reads as still running.

## Queue a second message

Type again while the turn is still running. The composer never locks:

- The message is shown as its own pending row rather than sent.
- Remove a pending row to drop it, or edit it to pull it back into the composer;
  re-sending puts it at the **tail**, behind anything queued before it.
- When the running turn ends, the head of the queue becomes the next turn.

Open the same conversation in a second tab: the pending rows are the same rows.
So are they on your phone, if the conversation is paired to a channel.

## Stop a turn

Press stop. The turn ends where it is, whatever it had already written is kept
and persisted, and **the queue pauses** — nothing behind it starts on its own.
Your next message resumes the queue in order.

## Watch a turn you started somewhere else

If a conversation is paired to an IM channel it carries a badge naming that
channel. Send a message to the bot from your phone, then open that conversation
on the page mid-turn: the turn is replayed from its beginning and then followed
live. Stopping it from the page stops it for the phone too — one turn, two
windows.

## Change what a conversation runs on

The bar above the thread reads and sets the agent, the model and the effort.
Changing the model takes effect on the next turn; the working directory and the
agent's session are preserved, and clearing a value reverts to the agent's own
default.

## Rename, archive, restore, delete

- **Rename** from the conversation's own menu. Once you have named it, Coffer
  never renames it for you.
- **Archive** moves it out of the active list into the archived list without
  destroying anything. An archived conversation opens read-only, with a restore
  control where the composer was.
- **Restore** puts it back in the active list.
- **Delete** removes the conversation and its messages, and cancels any turn
  still running on it. This is the destructive one.

Left alone, a conversation with no new message is auto-archived after 7 days and
an archived one is deleted 30 days later. Both windows are yours to change — or
to set to keep-forever — on the retention surface, alongside every other
retained table.

## The same operations over HTTP

```bash
# The daemon token is in ~/.coffer/daemon.json.
COFFER_TOKEN=$(jq -r .token ~/.coffer/daemon.json)
API=http://127.0.0.1:8000/api/v1

# Which agents can run a turn, and what can each be put on?
curl -sH "X-Coffer-Token: $COFFER_TOKEN" $API/agent-providers
curl -sH "X-Coffer-Token: $COFFER_TOKEN" $API/agent-providers/claude_code/models

# Start a conversation and send a message (202 — the reply is not in the response).
CONV=$(curl -sH "X-Coffer-Token: $COFFER_TOKEN" -H 'Content-Type: application/json' \
  -d '{"agent_key":"claude_code"}' $API/chat/conversations | jq -r .id)
curl -sH "X-Coffer-Token: $COFFER_TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' $API/chat/conversations/$CONV/messages

# Watch the turn. This is the only place turn output comes from.
curl -NsH "X-Coffer-Token: $COFFER_TOKEN" $API/chat/conversations/$CONV/events

# Stop it, keeping what it wrote; the queue pauses.
curl -XPOST -sH "X-Coffer-Token: $COFFER_TOKEN" $API/chat/conversations/$CONV/interrupt
```

## When something looks wrong

- **A reply that never arrives after a restart** should not exist: the startup
  sweep marks it failed. If you see one, the sweep did not run.
- **"unknown agent"** on a turn means the conversation names an agent this host
  has no provider for — the agent list shows which exist and which are
  installed.
- **A conversation that will not resume** is the one case that self-heals: a
  session id the agent has forgotten costs one silent retry as a fresh session,
  not the conversation.
- **A failed turn** shows one inline banner above the composer with a Retry that
  re-sends the message that failed.
