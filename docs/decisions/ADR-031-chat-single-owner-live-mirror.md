# ADR-031 — Chat Is the Owner's Single-Owner Live Mirror

> 中文版: [ADR-031-chat-single-owner-live-mirror.zh.md](./ADR-031-chat-single-owner-live-mirror.zh.md)

- **Status:** Accepted
- **Date:** 2026-06-20
- **Deciders:** Yuxing Wu
- **Spec:** [008-agent-chat](../../specs/008-agent-chat/spec.md) (repositioning + turn-lifecycle change — no new spec number; `spec.md` is updated before implementation)
- **Narrows:** [ADR-021](./ADR-021-chat-as-vault-console.md) job 2 (channel observe) — from *observe* to *observe + interrupt + inject*
- **Builds on:** [ADR-024](./ADR-024-builtin-agent-is-internal-capability.md) (chat talks to managed agents only), [ADR-025](./ADR-025-remove-tool-approval.md) (full-permission, no approval seat), [ADR-014](./ADR-014-channel-adapter-framework.md) (channel turn seams), Spec [009-channels](../../specs/009-channels/spec.md)

## Context

Chat (Spec 008) has been repositioned twice and had its central concept removed,
always with the same argument — *Coffer is a vault, not an actor; a browser chat
that competes with the agents' own UIs and with IM has no durable usage*:

- **ADR-021** → *Vault Console* (talk to the vault + observe/approve channel turns).
- **ADR-024** retired the built-in chat persona; chat talks to managed agents
  (`claude_code`, `codex`) only; the surface reverted to *Chat*.
- **ADR-025** removed tool-approval; the channel job shrank from *observe + approve*
  to *observe* only.

The result is a half-amputated surface nobody had decided to keep or kill. The
code shows it: ~600 lines of legacy CLI adapters kept "for tests only", an
untyped `agent_config` JSON blob, and a `spec.md` that papers over ADR-024 drift
with a prose disclaimer instead of a rewrite.

This ADR picks chat's one irreplaceable job and commits to it.

The decisive constraint, surfaced while reviewing the channel bridge: Coffer
channels are **owner-paired** (Spec 009 — "a paired **owner** chats … from the IM
app"). The "IM peer" is therefore the *same person* — the owner on their phone —
not a third party. So "take over an IM conversation" is **cross-surface
continuity for one owner**, not multi-human collaboration. This removes the entire
multi-human dimension: no peer-identity model, no "who may interrupt whom", no
message-visibility rules.

## Decision

**Chat is the desktop surface of the same conversations the owner also drives
from their phone (IM).** One owner, one conversation timeline, two screens.
Behind a conversation is one real agent session (one `--resume` session, one
working directory), so a turn started on the phone and a turn continued on the
desktop hit the **same** session.

From the desktop the owner can **observe** any conversation live (including turns
kicked off from the phone, token by token), **interrupt** a running turn, and
**inject / continue** by typing freely — messages queue, never block.

### 1. A live conversation bus (the one new capability)

Of observe / interrupt / inject, only **observe** is actually missing today.
Interrupt already works cross-surface (the process-global `_ACTIVE_TURNS` lives in
the single daemon). Inject is a frontend gap — `POST /conversations/{id}/messages`
already accepts any conversation id. Observe is the gap: the web can only
live-stream a turn it started; a turn started from IM is seen only by 2-second
polling of persisted rows.

So decouple **starting a turn** from **consuming its events**. Each conversation
gets a **broadcaster** that (a) appends each `AgentEvent` to a **ring buffer** of
the current turn's events and (b) fans it out to every attached subscriber queue.
Two endpoints:

- `POST /conversations/{id}/messages` — **starts/enqueues** a turn and returns
  immediately; it no longer owns the event stream.
- `GET /conversations/{id}/events` (SSE) — **subscribe**: on attach, replay the
  ring buffer (catch up on what streamed before you attached), then stream live;
  when no turn is in flight, hold open with heartbeats and deliver the next turn
  whenever it starts, from any surface.

**Single event path:** all event consumption goes through the subscribe stream;
POST is fire-and-return. "Observe a turn I started" and "observe a turn the phone
started" then travel the same code — the sender is not a special case — and the
ring buffer guarantees the sender misses no early events.

### 2. Send freely; a FIFO pending queue (amends FR-018)

The "reject a second message; lock the composer" rule (FR-018) is replaced:
the composer **never locks**; an over-sent message **enqueues**. Each conversation
holds an in-memory **pending queue**. When the current turn completes, the
orchestrator dequeues the head, commits it as the next user message, and runs its
turn. The one-turn-per-conversation invariant **stays** — processing is sequential;
only the response to over-sending changes (queue, not reject).

- **Sequential, not coalesced.** Each queued message is its own turn, FIFO.
- **Pending is uncommitted.** Queued messages are not written into the committed
  message sequence; they surface as removable "pending chips" and are committed
  (taking the next `seq`) only when their turn starts. This keeps user/assistant
  alternation and `--resume` feeding clean and ordered.
- **Interrupt = stop the current turn + pause the queue.** Otherwise the next
  queued message would immediately fire into the turn you just stopped. The chips
  remain; the owner removes them, clears them, or resumes.
- **Cross-surface advance.** The pending queue is the web composer's; it
  auto-advances after *any* turn on the conversation ends — including an
  IM-driven one — so a desktop message queued behind a phone-started turn still
  runs when that turn completes. A message arriving *from* IM while a turn is in
  flight is held by the channel's own inbound buffering (Spec 009), not this
  queue; v1 does not merge the two into a single physical FIFO (the channel
  adapter keeps its per-peer buffer), so the cross-surface guarantee is
  "a desktop send is never rejected and runs in order", not "IM and web share one
  queue object".
- **Queue state rides the bus.** A `QueueChanged` event broadcasts the ordered
  pending items so every subscriber — a second tab, the phone — renders the same
  chips, making "two screens, one timeline" true for not-yet-processed messages.
- **In-memory, v1.** The pending queue is lost on a daemon restart (never
  committed) — consistent with "an in-flight turn is marked failed on restart".

### 3. Collapse origin; keep the return address

Under the single-owner premise the peer is always the owner, so the web-vs-channel
**dichotomy collapses as a concept**: one unified conversation list, one composer,
one subscribe stream — no `origin`-based branching. But `channel_name` /
`peer_chat_id` are the **return address** for pushing the agent's output back to
the IM app and cannot be deleted. So: drop `origin` and `peer_display_name`; keep
`channel_name` / `peer_chat_id` as an optional `channel_binding` (a conversation
"has a binding" iff `channel_name` is set); the desktop shows a small "also on
Telegram/SeaTalk" indicator when one exists.

### 4. Cleanup the dead positionings left behind

Rewrite Spec 008 `spec.md` / `data-model.md` / `contracts/api.openapi.yaml` to
match ADR-024 + this positioning instead of the prose disclaimer (delivered with
this change).

Two further cleanups were **deferred from the live-mirror change** (they are
independent of the live-mirror seam and touch the *active* coding-agent
providers, so they were kept out of that already-large change to avoid risking
the working `claude_code` / `codex` adapters):

- **(a) Delete the legacy CLI adapters** (`cli_agent.py`, `cli_providers.py`)
  after extracting the shared helpers (`ParseState`, `SessionSink`,
  `last_user_text`) the live adapters still import into a small
  `adapter_support.py`. — **DELIVERED** (follow-up PR).
- **(b) Replace the untyped `agent_config` blob** with a typed
  `AgentConfig { cwd, session_id, model }` (a frozen domain dataclass the
  providers validate into and persistence serializes to/from the JSON column;
  no wire-contract change). — **DELIVERED** (follow-up PR).

### Invariants

- **Same seams, no parallel path.** The desktop drives turns only through the
  existing `ConversationPort` / `TurnPort` / orchestrator; an agent cannot tell a
  desktop turn from a phone turn. The subscribe stream is read-only observation +
  the existing interrupt; it introduces no privileged turn path.
- **`_ACTIVE_TURNS` stays process-global.** Single user, single daemon; horizontal
  scaling is YAGNI. The broadcaster and the pending queue live in the same process.
- **No multi-human model.** The single-owner premise is load-bearing; peer
  identity and message-visibility rules are explicitly out of scope.
- **Managed agents only.** ADR-024 stands — no built-in chat persona; the local
  model remains internal-only behind `coffer__*`.

## Alternatives considered

### A — Keep observe-only; do not add interrupt/inject

**Rejected.** The owner explicitly wants to grab the wheel from the desktop
(stop a runaway turn, keep typing). Observe-only leaves the phone-started
conversation un-steerable from the desk — the one thing the desktop seat is for.

### B — Live bus only; skip the cleanup and the origin collapse

**Rejected.** Functional but leaves the residue the ADR churn created (legacy
adapters, untyped config, spec drift, the meaningless web/channel split). Coffer's
posture is delete-over-add; the cleanup is most of the value and the new code is
small.

### C — Keep POST streaming back *and* add a subscribe stream

**Rejected.** Two event paths, redundant. The single subscribe path makes the
sender not a special case and removes a class of races; the ring buffer covers
the sender's early events.

### D — Coalesce all pending messages into one combined next turn

**Rejected for v1** (kept as a one-line switch). The owner asked to process them
"one by one"; sequential FIFO is the predictable default. Coalescing (fuller agent
context, fewer turns) can be reconsidered if rework-churn proves annoying.

### E — Persist the pending queue across restarts

**Rejected for v1 (YAGNI).** Daemon restarts are rare; not-yet-committed messages
dropping on restart matches the in-flight-turn-marked-failed story. Persisting as
`queued` rows is a later hardening.

## Consequences

- Spec 008 (`spec.md`, `spec.zh.md`, `data-model.md`,
  `contracts/api.openapi.yaml`) is rewritten: a new `GET .../events` subscribe
  endpoint; POST messages becomes fire-and-return; FR-018 amended (queue, not
  reject); `origin` collapsed; the `QueueChanged` event added; the built-in-persona
  drift removed.
- The conversation schema drops `origin` + `peer_display_name` (Alembic migration,
  SQLite `batch_alter_table`); `channel_name` / `peer_chat_id` stay as the
  `channel_binding`. The Spec 009 channel layer is updated where it wrote those
  fields.
- The frontend replaces the per-turn POST SSE + 2-second polling with one
  persistent `GET .../events` subscribe stream; the composer never locks and
  renders pending chips.
- Legacy CLI adapter deletion (part 4a) and `agent_config` typing (part 4b)
  are both **delivered** in follow-up PRs (move 3, part 4).
- ADR-021 is **narrowed** (not superseded): its channel-observe job is widened to
  observe + interrupt + inject; its multi-human "approval seat" framing is already
  gone (ADR-025).
- No built-in-persona change (ADR-024 stands); no credential-handling change.
