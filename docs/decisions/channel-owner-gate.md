# A Channel Answers Only Its Paired Owner, and Fails Closed in Groups

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Yuxing Wu
**Related**: spec channels ("Pair exactly one owner with a single-use code", "Gate inbound traffic on sender identity", "Act in a group only on an addressed message from the owner", "Treat an addressed group chat as its own peer", "Configure when the bot answers in a group", "Limit the agents a channel may drive to its scope", "Pair by a one-tap start link");
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Managed Agents Run With Full Permissions](managed-agents-run-with-full-permissions.md),
[Per-Agent Resource Scope](per-agent-resource-scope.md), [Resource Identity Is an Immutable UID](resource-identity-is-an-immutable-uid.md);
PRs #59, #245, #266, #380

## Context

A channel lets whoever talks to the bot drive a managed agent that runs with
full permissions on the owner's machine — shell, file writes, network — with no
per-tool approval ([Managed Agents Run With Full
Permissions](managed-agents-run-with-full-permissions.md)). The bot is also
reachable by anyone on the platform: a Telegram bot by username, a SeaTalk bot
by anyone in the organisation, and both can be added to groups where many
people can @mention them. So the question "who may start a turn" is the
security boundary of the whole channel plane, and it has to hold in three
different settings:

- **A direct chat**, where the platform's chat id identifies one person.
- **A group**, where one chat id is shared by every member, so the chat id
  proves nothing about the sender.
- **A transport quirk**, where an update arrives without a sender id at all.

And a second, narrower question: of the agents registered on this machine,
which may this bot drive? A work bot in a team group should not be able to
switch to an agent the owner keeps for something else.

## Options Considered

### Option A — A single-use pairing code binds one owner; every turn is gated on the owner's sender id; groups fail closed (chosen)

**Pairing.** The owner asks the UI or CLI for a code and sends it to the bot
from their own account. The code (`application/channel/pairing.py`) is 8
characters from an alphabet without `0`, `O`, `1` or `I`, single use, valid
for 1 hour, and burned after 10 wrong guesses. It is held in memory only, so a
daemon restart discards it. A Telegram bot also offers a one-tap start link
carrying the code (`/start <CODE>`), which goes through the same gate. A
successful claim records the sender's platform id (`sender_id` — Telegram
`from.id`, SeaTalk `employee_code`) on the peer row and un-pairs every other
sender's rows, so a channel has exactly one owner identity; the claim is
audited (`channel_paired`).

**Direct chats.** A message from a chat with no peer row is only ever a
pairing attempt; anything that is not the code is ignored with no reply, so the
bot never reveals to a stranger that it is alive. A message from a paired chat
whose sender id differs from the stored one is ignored silently too.

**Groups.** A group message passes, in order:

1. `require_mention` (default on): an un-addressed message — no @mention, no
   reply to the bot — is dropped.
2. `ignore_other_mentions` (opt-in): a message that @mentions another human is
   dropped, so the bot never butts into traffic aimed at a person.
3. The channel must have an owner sender id at all; a group @mention cannot
   bootstrap pairing.
4. The message's sender id must equal the owner's. An **empty** sender id is
   refused like a wrong one — a group is shared, so "the transport could not
   tell me who" must never mean "assume the owner". A refused addressed message
   gets a short "Not authorized" reply rather than silence, because the sender
   deliberately addressed the bot in front of others and silence reads as a
   broken bot.
5. The owner's first addressed message in a group creates that group's own
   peer row, inheriting the owner's sender id, so the group has its own
   conversations separate from the owner's DM.

(`application/channel/inbound.py`, `on_message`.)

**Scope, read inverted.** For every other kind, a resource's per-agent scope
says which agents it is delivered to; for a channel it says which agents the
channel **may drive** ([Per-Agent Resource Scope](per-agent-resource-scope.md)).
`/agent` lists, offers as a card and validates only agents inside the scope
(`application/channel/agent_routing.py`); a thread's sticky agent that falls
outside a narrowed scope falls back to the default. The default agent must lie
inside a non-empty scope — both the config write path and the scope write path
(`validate_scope_for` in `application/channel/kind.py`) refuse to separate
them — and a channel that can drive nothing (no default agent, an empty
allow-list, or a default agent not registered here) is not started at all
(`application/channel/wanted.py`), so it never accepts a message only to
refuse it.

Pros: the code proves both that the owner controls the account and that the
transport round-trip works, in one step. A mistyped id cannot bind the wrong
person because the owner never types an id. Groups cannot be driven by anyone
but the owner even when the platform's payload is incomplete. The scope turns
"which agents" into the same reach vocabulary as every other kind.

Cons: one owner per channel — a team cannot share one bot as several
principals. A daemon restart loses an outstanding code (re-issuing is one
step). A DM peer paired before sender ids were recorded has no stored sender
id and keeps a chat-id-only gate, which is sound only because a DM's chat id
is its person's id.

Wins because it is the smallest mechanism that makes the bot's reachability
irrelevant: being able to message the bot grants nothing.

### Option B — An allowlist of platform user ids entered in config

How it works: the owner types their Telegram user id or SeaTalk employee code
into the channel config; the gate compares against it.

Pros: no pairing step; survives restarts trivially; could list several people.

Cons: the owner has to find their own platform id, which neither platform
shows plainly; a typo binds silently to someone else or to nobody, and nothing
proves the transport actually works until the first message fails. A list of
several principals reopens every question the single-owner premise closes —
whose conversation, who may interrupt whom ([Chat Is a Single-Owner Live
Mirror](chat-single-owner-live-mirror.md)).

Loses because pairing proves identity and connectivity at once, and an entered
id proves neither.

### Option C — An open bot: anyone who can reach it may drive it

How it works: no gate; rely on the bot's username or organisation being
private.

Pros: zero setup.

Cons: a full-permission agent on the owner's machine driven by anyone who
finds the bot or shares a group with it. Obscurity is not a boundary on a
platform whose bots are discoverable by username.

Loses outright.

### Option D — Per-message or per-tool approval by the owner

How it works: any sender may start a turn, but each turn or each tool call
waits for the owner to approve it from another surface.

Pros: fine-grained; a stranger's request could be granted case by case.

Cons: Coffer built and then removed a per-tool approval system — no approval
ever ran end to end, and an agent that waits on a human for every shell call
is not usable from a phone ([Managed Agents Run With Full
Permissions](managed-agents-run-with-full-permissions.md)). Approving whole
messages from strangers still requires the owner to be watching, and a missed
approval stalls a group conversation.

Loses because the gate belongs at who may speak, not at what the agent may do
once spoken to.

### Option E — A shared password or passphrase in the message

How it works: a message is accepted if it carries a configured secret, or the
first message in a chat must carry it.

Pros: works without knowing platform ids.

Cons: a secret typed into a group is disclosed to the group; a reusable
passphrase, unlike a single-use code, stays valid after it leaks; it
authenticates a message rather than a person, so anyone who ever saw it keeps
access.

Loses because a single-use, short-lived code bound to a sender id gives the
same convenience without a long-lived secret.

## Decision

A channel has exactly one owner, bound by claiming a single-use pairing code
from the owner's own account; the claim records the owner's platform sender id.
Every inbound message and card tap is gated on that sender id. In a direct
chat, anything not from the owner is ignored silently. In a group, the bot acts
only on an addressed message (`require_mention`, default on; optionally
`ignore_other_mentions`) whose sender id is proven to be the owner's; an
unproven or foreign sender is refused with a "Not authorized" reply. A
channel's scope is the set of agents it may drive: it narrows `/agent`, bounds
the sticky agent, must contain the default agent, and a channel whose scope
admits nothing it can route to does not run.

Rules a future change must respect:

- An empty or missing sender id never passes a group gate.
- No path binds an owner except claiming a code.
- A stranger's DM gets no reply of any kind.
- Scope narrowing is enforced in the one routing module every surface reads.

## Consequences

- The channel plane can grant agents full permissions because the gate sits in
  front of them; weakening this gate weakens that decision too.
- Every new transport must supply a stable per-sender id and say in its child
  spec what it is; a transport that cannot is usable in DMs only.
- Card taps are owner-gated exactly like messages, so a button pressed by
  another group member does nothing; for the same reason Telegram's draft stop
  control (whose update names no sender) is offered in DMs only.
- Pairing and code issuance are the channel events that audit; a turn does not
  ([Audit and Retention](audit-and-retention.md)).
- Enforced by: `application/channel/pairing.py`, `application/channel/inbound.py`,
  `application/channel/agent_routing.py`, `application/channel/wanted.py`,
  `application/channel/kind.py`.
