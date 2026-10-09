# Channels Are Machine-Local Resources, Like Agents

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing (owner)
**Related**: [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced](reach-is-machine-local-stored-by-uid-never-synced.md), [Channels Are Thin Transport Adapters Over One Shared Core, Supervised In-Daemon](channel-adapter-framework.md), [Telegram Inbound Is a Long Poll That Commits the Offset After Dispatch](telegram-long-polling.md), [SeaTalk Inbound Is One Outbound WebSocket, Through an Operator-Supplied SDK](seatalk-websocket-inbound.md), [A Channel Answers Only Its Paired Owner, and Fails Closed in Groups](channel-owner-gate.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), PRs #382, #385

## Context

A channel is a bot connection: a Telegram bot or a SeaTalk app that a person
talks to from a phone, answered by an agent on a computer. Whether channels
should travel with the vault has been decided twice. On 2026-09-14 (PR #382)
they stopped syncing, so a second machine would not also answer the bot. On
2026-09-15 (PR #385) they synced again, with a `runs_on` field naming the one
machine whose daemon starts the adapter, on the reasoning that `runs_on` solved
the double-answer problem the first decision was avoiding.

On 2026-10-09 the second design was found to be inconsistent in itself. The
synced channel document carries three kinds of field that mean something only
on one machine:

- `default_agent` is the uid of an agent, and agents are machine-local
  resources, so on any other machine the uid dangles.
- `runs_on` is a machine id, and `directories` are paths on one disk.
- Which agents the channel may drive lives in `local/reach.json`, so the
  invariant "the default agent is inside the channel's scope" was split between
  a synced document and a local record; the reach ADR itself said so.

The platforms impose the underlying limit. Telegram allows one poller per bot
token and answers a second with `409 Conflict`; SeaTalk drops the earlier
connection when a second one for the same app arrives. A channel is therefore
inherently a thing that runs in exactly one place.

How comparable products treat it: OpenClaw has one Gateway own all messaging
connections, and a second Gateway uses its own bot token, config and state
directory (sharing config causes contention). cc-connect keeps its config in
`~/.cc-connect/config.toml` on each machine, one token per project. Claude
Code's Telegram channel plugin allows one poller per token, so it writes a
`bot.pid` and kills the previous holder. Codex Remote and Claude Remote
Control pair a phone to one specific machine. None of them syncs bot
configuration between machines.

## Options Considered

### Option A — Keep syncing the channel, keep `runs_on`, and move every machine-specific field out of the synced document

`default_agent` becomes an agent type key (`claude_code`, `codex`) instead of a
uid, `directories` moves to a local record, and the scope check reads only
portable data. `runs_on` stays as the single machine-specific field.

Pros: adding a machine does not need the channel to be re-created; the bot's
transport settings are entered once.

Cons: it keeps a special form of document that is "synced but effective on one
machine only", with its own gate in the runtime, its own states in the UI
("bound to another machine", "unbound", "unknown machine"), a takeover flow and
a fault when the named machine leaves the registry. The portable remainder is
small: a name, a platform, and a secret reference. Pairings would still have to
be machine-specific, because a chat paired on one machine means nothing to a
bot another machine is not polling. Every future channel field would need the
question "does this travel?" answered by someone who remembers.

Loses because it spends the most machinery to preserve the least value: what
survives the carve-out is a name and a secret ref.

### Option B — The channel is a machine-local resource, like an agent (chosen)

The channel's file lives in `~/.coffer/local/resources/channel/<name>.json`, in
the `local` storage class, never in `vault/`, never committed, never synced.
Its pairings live in `~/.coffer/local/channel-peers.json`, keyed by channel
uid. Its reach (`enabled` and scope) stays in `local/reach.json` as before.
`runs_on` is deleted: a channel that is switched on runs on the machine that
holds it.

Pros: every reference in the document (`default_agent`, `directories`, the
scope) is now consistent because it all lives on one machine; the
default-agent-inside-scope invariant is held by one machine's data; the
double-answer problem cannot arise from sync, so the gate, the three states and
the takeover flow disappear; it matches every comparable product.

Cons: moving to a new machine means creating the channel there, picking the
existing secret and pairing again. This is rare, and pairing is a single
message to the bot.

Wins because it removes a category of state rather than managing it, and the
cost lands only on a rare action.

### Option C — Status quo: sync with `runs_on`, with uid references inside

What shipped after PR #385.

Pros: no work; moving a bot is a one-field change.

Cons: the dangling `default_agent` on every machine that does not hold the
agent; the split invariant; `directories` that are paths on someone else's disk;
a machine id inside a document every machine holds, which needs the
[machine registry](sync-machine-identity.md) to stay meaningful.

Loses because the inconsistency is structural. Nothing in the design can make a
local uid valid on a second machine.

### Option D — Sync the channel but start it nowhere until a machine claims it

The file travels; an adapter starts only where the person has claimed the
channel on this machine.

Pros: the bot's transport settings are entered once.

Cons: it is Option A with the binding stored per machine instead of in the
document: the same synced-but-local document, the same dangling fields, and a
claim state to explain.

Loses for the same reason as A.

## Decision

A channel is a machine-local resource, in the same storage class as an agent.
Its file is `local/resources/channel/<name>.json`, its pairings are
`local/channel-peers.json` keyed by channel uid, and neither is ever in the
vault, committed or synced. There is no "runs on" setting; a switched-on channel
runs on the machine that holds it. The channel's secrets remain ordinary secrets
cited by reference, and their ciphertext travels only when the person has opted
the remote into secrets
([Secrets Cross Machines Only as Ciphertext](secrets-cross-machines-only-as-ciphertext.md)).

Rules a later change must respect:

- No field of a channel may name a machine, and no vault document may reference
  a channel by uid.
- Using the same bot on another machine means creating the channel there
  (choosing the existing secret) and pairing again. Because a bot token
  tolerates one consumer, the person switches the old machine's channel off or
  deletes it; Coffer cannot do it for them.

## Consequences

- Channels leave the vault's "what travels" list and join the agents on the
  machine-local side; the sync, the machine registry and the reconciler no
  longer know about channels.
- The runtime's gate has two parts, enabled and routable.
- A one-time startup migration (`infrastructure/channel/move_to_local.py`)
  moves each machine's own channels (bound to it, or to no machine) and their
  pairings into `local/`, reading them from before the deletion when another
  machine got there first, and deletes the vault copies in one commit. It is
  removed once every machine has run it.
- Enforced by: the `channel` kind's storage class, the channel runtime's gate in
  `application/channel/wanted.py`, and the `local/` path helpers in
  `infrastructure/vault/home.py`.
