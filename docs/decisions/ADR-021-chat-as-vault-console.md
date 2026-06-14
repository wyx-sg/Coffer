# ADR-021 — Reposition Agent Chat as the Vault Console

> 中文版: [ADR-021-chat-as-vault-console.zh.md](./ADR-021-chat-as-vault-console.zh.md)

- **Status:** Accepted
- **Spec:** [008-agent-chat](../../specs/008-agent-chat/spec.md) (repositioning — no new spec number; Spec 008 `spec.md` is updated before implementation)
- **Related:** [009-channels](../../specs/009-channels/spec.md) ([ADR-014](./ADR-014-channel-adapter-framework.md), shared turn/approval seams), [ADR-022](./ADR-022-cross-agent-transcript-history.md) (cross-agent history surface that lives in this console), [007-memory](../../specs/007-memory/spec.md) (the vault the console talks to)

## Context

Spec 008 Agent Chat shipped as a full multi-agent chat client: three agents
(`builtin` Coffer Assistant, `claude_code` via the Python SDK, `codex` via the
`codex app-server` subprocess), an agent picker, a working-directory picker, a
model picker, conversation history, and per-tool approval cards.

But the realistic surfaces for talking to a coding agent are (a) the agent's
**own** UI — the focused place you write code — and (b) **IM** — the async,
mobile, away-from-keyboard place. A browser chat client that competes with both
has no durable usage and is off-mission: Coffer's value is the vault (memory,
skills, knowledge, aggregated MCP, sync), not being yet another chat front-end.
"A chat page with no real usage" also fails the project's deliverable bar
(every shipped surface must have real usage).

Two roles, however, are **unique to Coffer** and served nowhere else:

1. **Talking to the vault itself.** The `builtin` agent is already an in-process
   MCP client of Coffer's own gateway (memory / KB / skills / aggregated MCP
   tools, session id `coffer-builtin-agent`). That is a console / playground for
   the vault, not a coding chat.
2. **A human-in-the-loop seat for channel/IM-driven conversations.** Channels
   (Spec 009) already create conversations and route tool approvals through the
   **same** `ConversationPort` / `TurnPort` seams the web UI uses; an agent
   cannot tell a channel turn from a UI turn. The web UI is the natural place to
   **observe** those conversations and **take the approval seat** for them.

## Decision

Reposition the Agent Chat surface as the **Vault Console**. Its job is:

1. **Converse with the vault** through the `builtin` agent, and
2. **Observe and approve** channel/IM-driven conversations.

Explicitly **de-scope** "use Coffer as your day-to-day in-browser coding chat."
Three concrete moves:

1. **Builtin agent → vault console / playground.** Reframe naming, empty state,
   and CTA away from "general assistant" toward "ask your memory / skills / KB."
   Surface, per turn, which memory facts / KB docs / skills / aggregated MCP
   tools the turn actually touched, so the console doubles as a way to _inspect_
   what an agent would get from the vault.
2. **Origin-aware conversation list + approval seat.** The conversation list
   distinguishes origin (web draft vs. channel peer), shows the peer identity for
   channel-originated conversations, and surfaces pending tool approvals
   prominently. Approving from the web `ApprovalCard` is equivalent to tapping
   the IM approval button — both resolve the same `submit_approval`.
3. **CLI agents reframed, not removed.** `claude_code` / `codex` stay available
   but are repositioned: not "your daily coding chat," but (a) **test-drive**
   targets and (b) the conversations **IM drives that you observe/approve here** —
   and, via [ADR-022](./ADR-022-cross-agent-transcript-history.md), the source of
   a unified, searchable history.

Per Constitution Principle II, Spec 008 `spec.md` and its acceptance scenarios
are updated to this positioning **before** implementation; this ADR records the
direction.

### Invariants

- **Same seams, no parallel path.** The Vault Console drives turns and
  approvals only through `ConversationPort` / `TurnPort`, exactly as channels
  do. It introduces no privileged turn or approval path; an agent cannot
  distinguish a console turn from a channel turn.
- **Approval parity.** A pending tool approval is resolvable from _either_ the
  web `ApprovalCard` _or_ the IM button; both call `submit_approval`. The
  console gets no special approval authority.
- **No daily-driver creep.** Affordances that only make sense for "Coffer as
  your primary coding chat" (rich coding UX competing with native clients) stay
  out of scope unless a future spec deliberately re-opens that positioning.

## Alternatives considered

### A — Keep positioning it as a full multi-agent chat client

**Rejected.** No durable usage against the agents' own UIs and IM; off-mission
(Coffer is a vault, not a chat client); fails the real-usage deliverable bar.

### B — Cut the chat surface entirely

**Rejected.** That discards two genuinely unique roles (vault console + approval
seat) and the already-built shared turn/approval seams. Channels still need a
human approval seat somewhere; the console is the cheapest home for it.

### C — Split into two separate pages (a console page + a channels-approval page)

**Rejected for now.** Both rely on the same conversation / turn / approval
machinery and the same thread UI. One origin-aware surface is simpler and avoids
duplicating the thread component; a split can be revisited if the two roles
diverge.

## Consequences

- Spec 008 `spec.md`, UI copy, and the builtin-agent detail-page CTA are updated
  to the Vault Console positioning.
- Channel-originated conversations become first-class in the conversation list
  (origin badge, peer identity, pending-approval affordance).
- `continue`/`resume` of foreign agent sessions stays out of scope (see
  [ADR-022](./ADR-022-cross-agent-transcript-history.md)).
- This is positioning + frontend surfacing; the backend turn / approval /
  channel machinery is reused unchanged.
