# Chat Is a Single-Owner Live Mirror

**Status**: Accepted
**Date**: 2026-06-20
**Deciders**: Yuxing Wu
**Related**: spec chat ("Send fire-and-return and stream output over one subscription", "Replay the in-flight turn to late subscribers", "Queue messages sent during a turn", "Pause the pending queue on interrupt", "Show every conversation on the Chat page", "Sweep streaming rows left by a crashed daemon"); spec channels;
[Coffer Model Is an Internal Engine](coffer-model-is-an-internal-engine.md) (chat talks to managed agents only),
[Managed Agents Run With Full Permissions](managed-agents-run-with-full-permissions.md) (no approval seat),
[Channels Are Thin Transport Adapters](channel-adapter-framework.md) (the channel turn seam),
[Driving Agents Through the SDK and App-Server](driving-agents-through-sdk-and-app-server.md),
[Resource Identity Is an Immutable UID](resource-identity-is-an-immutable-uid.md);
research note [Agent chat clients](../research/agent-chat-clients.md)

## Context

The web Chat page had been repositioned twice and had its central concept
removed, always on the same argument — *Coffer is a vault, not an actor; a
browser chat that competes with the coding agents' own UIs and with IM has no
durable usage*. It was first a **Vault Console** (talk to the vault, observe
and approve channel-driven turns); the built-in chat persona was then retired,
so chat talked to managed agents only; then tool approval was removed, and the
channel job shrank from *observe + approve* to *observe*. The page was deleted
on 2026-09-10 (every conversation in the vault had come from a channel, so the
page looked unused) and restored on 2026-09-12, because watching and steering
from a desktop a turn started from a phone is something the owner wants and
no channel can do.

The constraint that decides the design: Coffer channels are **owner-paired**
([Channel Owner Gate](channel-owner-gate.md)). The person on the IM side is the
owner on their phone, not a third party. So "take over an IM conversation from
the browser" is **cross-surface continuity for one person**, not multi-human
collaboration. That removes the whole multi-human dimension: no peer-identity
model, no "who may interrupt whom", no message-visibility rules.

What was actually missing, of observe / interrupt / inject:

- **Interrupt** already worked across surfaces — one daemon holds every
  in-flight turn.
- **Inject** was a frontend gap.
- **Observe** was the real gap: the browser could stream only a turn it had
  started itself; a phone-started turn was visible only by polling persisted
  rows.

## Options Considered

### Option A — One conversation timeline on two screens: a per-conversation event bus, a shared FIFO queue, origin collapsed (chosen)

**A live conversation bus.** Starting a turn is decoupled from consuming its
events. Each conversation has a `ConversationBus`
(`application/chat/bus.py`) that buffers the current turn's events and fans
them out to every subscriber. Four routes carry it
(`surfaces/http/chat/turn_routes.py`):

- `POST /api/v1/chat/conversations/{id}/messages` starts or enqueues a turn and
  returns `202` at once; it does not stream.
- `GET /api/v1/chat/conversations/{id}/events` is the SSE subscription: on
  attach it replays the in-flight turn from its beginning, then streams live;
  with no turn running it stays open and delivers the next turn whichever
  surface starts it.
- `PUT /api/v1/chat/conversations/{id}/pending` replaces the pending queue.
- `POST /api/v1/chat/conversations/{id}/interrupt` stops the running turn and
  pauses the queue.

All consumption goes through the subscription, so "observe a turn I started"
and "observe a turn the phone started" are the same code, and the replay
buffer guarantees the sender misses no early events.

**Send freely; a FIFO pending queue.** The draft surface never locks. A message
sent during a turn is queued in memory; when the turn ends the orchestrator
commits the head as the next user message and runs it. One turn per
conversation still holds — processing is sequential and each queued message is
its own turn. Pending messages are not committed rows: they take a sequence
number only when their turn starts, and editing one pulls it back into the
draft. Interrupt stops the current turn **and** pauses the queue, so the next
message does not fire into the turn just stopped. The queue advances after any
turn ends, on either surface, and IM and web share one queue object per
conversation, so the pending chips show a phone-sent message and `/status`
counts a web-sent one. Queue changes ride the bus, so a second tab and the
phone see the same rows. The queue is lost on a daemon restart, like an
in-flight turn.

**Collapse origin; keep the return address.** With one owner, web-versus-channel
collapses as a concept: one draft surface, one subscription, no origin
branching. The channel's uid and the peer chat id stay on the conversation as
the return address for pushing output back to IM — a conversation "has a
binding" iff `channel_uid` is set — and the page shows an "also on
Telegram/SeaTalk" badge. The chat list shows every conversation whose
`owner` column is null; a conversation created on behalf of another surface
that owns it (a non-null `owner`) is kept out of the list but readable by id,
like any transcript (`infrastructure/chat/persistence.py`). No caller on the
main line sets `owner` today; the column exists so a surface that runs
conversations for itself does not flood the owner's list.

Pros: the owner can watch a phone-started turn token by token, stop it, and
keep typing, from the desktop; no event path is special-cased by sender;
adding a client is adding a subscriber.

Cons: the pending queue and the replay buffer live in memory; a daemon restart
drops uncommitted messages (an in-flight turn becomes a visibly failed row
through the startup sweep). One persistent subscription per open conversation
in the frontend.

Wins because it closes the one real gap (observe) with one mechanism and makes
the other two fall out of it.

### Option B — Observe only; no interrupt or inject

Pros: smallest change.

Cons: leaves a phone-started conversation un-steerable from the desktop — the
one thing the web seat is for.

Loses on the use case.

### Option C — Keep the POST streaming back and add a subscription beside it

Pros: the sender gets events without a second request.

Cons: two event paths for the same turn, and races between them; the sender
becomes a special case.

Loses because one subscription with a replay buffer covers the sender's early
events.

### Option D — Coalesce pending messages into one combined next turn

Pros: fuller context per turn, fewer turns.

Cons: the owner cannot tell which message the agent is answering; a queued
correction merges with the thing it corrects.

Loses on predictability; sequential FIFO is the default and coalescing
remains a small switch if rework churn proves annoying.

### Option E — Persist the pending queue

Pros: queued messages survive a restart.

Cons: a new durable state for a rare event, and queued rows would have to be
distinguished from committed ones everywhere messages are read.

Loses because daemon restarts are rare and dropping uncommitted messages
matches how an in-flight turn is treated.

### Option F — Delete the page

How it works — what was done on 2026-09-10.

Pros: a large surface that had never run is a liability.

Cons: removes the only place to watch and steer a phone-started turn from a
desktop.

Loses because the owner wants exactly that; the page was restored two days
later.

## Decision

The web Chat page is the second screen of the same conversations the owner
drives from their phone: one owner, one timeline, one real agent session per
conversation. Turns are started fire-and-return and observed through one SSE
subscription per conversation that replays the in-flight turn; messages sent
mid-turn join a FIFO queue shared by web and IM; interrupt stops the turn and
pauses the queue. Origin is not modelled; a channel binding is a return
address. Conversations with a non-null `owner` are not listed.

Invariants:

- **Same seams, no parallel path.** The page drives turns only through the
  conversation and turn ports; an agent cannot tell a web turn from a phone
  turn.
- **No multi-human model.** The single-owner premise is load-bearing.
- **Managed agents only.** No built-in chat persona and no approval seat.

## Consequences

- The conversation schema carries no origin and no peer display name; the
  channel uid and peer chat id are the binding.
- A new agent is one `AgentProvider` / `AgentAdapter` pair registered in
  `surfaces/http/chat_provider_wiring.py`; every surface resolves agents
  through the provider registry. A new client is one more bus subscriber.
- Chat stays inside its kind: the import-linter contract "Cross-kind imports
  forbidden (chat)" in `backend/pyproject.toml` has no exceptions, and the
  model catalogue reaches chat only through `ModelCatalogPort`, published by
  the composition root.
- A wedged turn is cancelled by the idle watchdog through the adapter's own
  interrupt path, and the startup sweep marks rows a crash left `streaming` as
  failed, so a restart is never silent.
- There is no `coffer chat` command group; the page and the HTTP routes are
  the ways to drive a conversation.
