# Chat Is a Single-Owner Live Mirror

> 中文版: [chat-single-owner-live-mirror.zh.md](chat-single-owner-live-mirror.zh.md)

**Status**: Accepted
**Date**: 2026-06-20 (page removed 2026-09-10, restored 2026-09-12; see Revision history)
**Deciders**: Yuxing Wu
**Related**: spec [`channels`](../../specs/channels/spec.md) — the turn platform (FR-043…FR-055) and the web Chat page (FR-072…FR-078);
[Built-in Agent Is Internal](builtin-agent-is-internal-capability.md) (chat talks to managed agents only),
[Remove Tool Approval](remove-tool-approval.md) (full permissions, no approval seat),
[Channel Adapter Framework](channel-adapter-framework.md) (the channel turn seams)

## Context

The web Chat page had been repositioned twice and had its central concept
removed, always with the same argument — *Coffer is a vault, not an actor; a
browser chat that competes with the coding agents' own UIs and with IM has no
durable usage*. It was first recast as a **Vault Console** (talk to the vault,
plus observe and approve channel-driven turns); then the built-in chat persona
was retired, so chat talked to managed agents only and the surface reverted to
*Chat*; then tool approval was removed outright, and the channel job shrank from
*observe + approve* to *observe*.

What that left was a half-amputated surface nobody had decided to keep or kill.

The decisive constraint, surfaced while reviewing the channel bridge: Coffer
channels are **owner-paired** — a paired *owner* chats from the IM app. The "IM
peer" is therefore the *same person*, the owner on their phone, not a third
party. So "take over an IM conversation from the browser" is **cross-surface
continuity for one owner**, not multi-human collaboration. That removes the
entire multi-human dimension: no peer-identity model, no "who may interrupt
whom", no message-visibility rules.

This record picks the page's one irreplaceable job and commits to it.

## Decision

**Chat is the web surface of the same conversations the owner also drives from
their phone.** One owner, one conversation timeline, two screens. Behind a
conversation is one real agent session (one resumed session, one working
directory), so a turn started on the phone and a turn continued in the browser
hit the **same** session.

From the page the owner can **observe** any conversation live — including turns
kicked off from the phone, token by token — **interrupt** a running turn, and
**inject / continue** by typing freely: messages queue, never block.

### 1. A live conversation bus

Of observe / interrupt / inject, only **observe** was actually missing. Interrupt
already worked cross-surface (a single daemon holds the in-flight turns). Inject
was a frontend gap. Observe was the real one: the browser could live-stream only
a turn it had started itself; a turn started from IM was visible only by polling
persisted rows.

So **starting a turn** is decoupled from **consuming its events**. Each
conversation gets a broadcaster that appends every turn event to a buffer of the
current turn and fans it out to every attached subscriber. Four routes carry it:

- `POST /api/v1/chat/conversations/{id}/messages` — **starts or enqueues** a turn
  and returns `202` at once. It does not own the event stream.
- `GET /api/v1/chat/conversations/{id}/events` — the SSE **subscription**: on
  attach it replays the in-flight turn from that turn's beginning, then streams
  live; with no turn running it holds open and delivers the next turn whenever it
  starts, from whichever surface starts it.
- `PUT /api/v1/chat/conversations/{id}/pending` — **replaces** the pending queue.
- `POST /api/v1/chat/conversations/{id}/interrupt` — **stops** the running turn
  and **pauses** the queue.

**One event path.** All consumption goes through the subscription; the POST is
fire-and-return. "Observe a turn I started" and "observe a turn the phone
started" then travel the same code — the sender is not a special case — and the
replay buffer guarantees the sender misses no early events.

### 2. Send freely; a FIFO pending queue

"Reject a second message and lock the composer" is replaced: the draft surface
**never locks**; an over-sent message **enqueues**. Each conversation holds an
in-memory pending queue; when the current turn completes, the orchestrator
dequeues the head, commits it as the next user message, and runs its turn. The
one-turn-per-conversation invariant **stays** — processing is sequential; only
the answer to over-sending changes.

- **Sequential, not coalesced.** Each queued message is its own turn, FIFO.
- **Pending is uncommitted.** Queued messages are not written into the committed
  message sequence; they surface as removable rows and take their sequence number
  only when their turn starts. Editing one pulls it back into the draft surface;
  re-sending puts it at the **tail**, because it is a new send.
- **Interrupt = stop the current turn + pause the queue.** Otherwise the next
  queued message would fire straight into the turn just stopped.
- **Cross-surface advance.** The queue auto-advances after *any* turn on the
  conversation ends — including an IM-driven one — so a message queued from the
  browser behind a phone-started turn still runs when that turn completes. A
  message arriving *from* IM mid-turn is held by the channel's own inbound
  buffering instead, so the guarantee is "a web send is never rejected and runs in
  order", not "IM and web share one queue object".
- **Queue state rides the bus.** A queue-changed event broadcasts the ordered
  pending items, so a second tab and the phone render the same rows.
- **In-memory.** The queue is lost on a daemon restart, consistent with an
  in-flight turn being marked failed on restart.

### 3. Collapse origin; keep the return address

Under the single-owner premise the peer is always the owner, so the
web-versus-channel dichotomy **collapses as a concept**: one conversation list,
one draft surface, one subscription, no origin-based branching. But the channel
name and peer chat id are the **return address** for pushing the agent's output
back to the IM app, so they stay as an optional channel binding — a conversation
"has a binding" iff a channel name is set — and the page shows a small "also on
Telegram/SeaTalk" badge when one exists.

### Invariants

- **Same seams, no parallel path.** The page drives turns only through the
  existing conversation and turn ports; an agent cannot tell a web turn from a
  phone turn. The subscription is read-only observation plus the existing
  interrupt; it introduces no privileged turn path.
- **No multi-human model.** The single-owner premise is load-bearing; peer
  identity and message-visibility rules are out of scope.
- **Managed agents only.** [Built-in Agent Is Internal](builtin-agent-is-internal-capability.md)
  stands — no built-in chat persona; the local model stays internal behind
  `coffer__*`.

## Consequences

- The page and its routes are described in spec [`channels`](../../specs/channels/spec.md)
  section G (FR-072…FR-078), on top of the turn platform (FR-043…FR-055); the
  contract lives in that spec's OpenAPI file.
- The conversation schema carries no `origin` and no peer display name; the
  channel name and peer chat id remain as the channel binding.
- The frontend holds one persistent subscription per open conversation rather
  than a per-turn stream plus polling; the draft surface never locks and renders
  pending rows.
- The Vault Console positioning is not restored: no vault persona, and no
  approval seat ([Remove Tool Approval](remove-tool-approval.md)).

## Alternatives Considered

**Keep observe-only; no interrupt or inject.** Rejected. The owner wants to grab
the wheel from the browser — stop a runaway turn, keep typing. Observe-only
leaves the phone-started conversation un-steerable from the desktop, which is the
one thing the web seat is for.

**Keep the POST streaming back *and* add a subscription.** Rejected. Two event
paths, redundant. The single subscription makes the sender not a special case and
removes a class of races; the replay buffer covers the sender's early events.

**Coalesce all pending messages into one combined next turn.** Rejected, kept as
a one-line switch. Sequential FIFO is the predictable default; coalescing (fuller
agent context, fewer turns) can be reconsidered if rework churn proves annoying.

**Persist the pending queue across restarts.** Rejected. Daemon restarts are
rare, and dropping not-yet-committed messages matches the in-flight-turn-marked-failed
story. Persisting them as queued rows is a later hardening.

**Delete the page instead.** This is what happened on 2026-09-10, and it is the
reason this record was gone for two days — see below.

## Revision history

- **2026-06-20 — accepted.** The live mirror as described above.
- **2026-09-10 — page removed, record deleted.** The argument: every conversation
  in the vault had been created by a channel, the live-mirror job was never
  exercised, and a large surface that has never run is a liability rather than an
  option. The turn platform underneath it survived whole, because channels run
  on it.
- **2026-09-12 — page restored, record reinstated.** The counterweight the
  removal itself recorded turned out to be the operative one: driving an agent
  from a phone while watching and steering it on a desktop is a thing the owner
  wants, and no channel can do it. The decision is unchanged from 2026-06-20 —
  only the routes are spelled out here now that they live in the channels spec
  rather than in a spec of their own.
