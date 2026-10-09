---
title: The reconciler
description: How Coffer keeps true what it writes into files it does not own — one level-triggered loop that compares every parameter, repairs only what its policy allows, previews without writing, and audits every repair.
---

# The reconciler

Much of what Coffer promises is a state of files it does not own: its own MCP entry in each agent's config, a link to each skill it delivers, a model provider's keys in an agent's settings, the hook that hands an agent its memory. Those files are rewritten by the agents' own CLIs, by other tools, by backups and by the person at the keyboard — often while Coffer is not running. The database says what should be true; only the file says what is. This page explains how Coffer closes that gap. The decision and the options weighed are in the ADR [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/one-level-triggered-reconciler-compares-parameters.md).

## Two lessons it is built on

**Presence is not correctness.** For months an installed memory hook kept passing an option the command-line tool had dropped. Every session started with a usage error, and Coffer's status said "installed" the whole time, because it recognised its hook by a marker and never read the arguments. Coffer's own MCP entry had the same shape: a launcher path an upgrade had moved, or an entry naming the wrong agent, still read as installed. So the reconciler judges every item by all of its parameters. Finding an entry by its marker is how an entry is *located*; comparing its parameters is how it is *judged current*.

**Events miss what happens between them.** Each kind used to check its own part on its own list of triggers — when a skill was enabled, when an agent was registered, at boot. Anything that changed between those moments, or while the daemon was down, stayed wrong until the next trigger that happened to cover it. The one part of Coffer that never had this problem was the one that simply looked again on a timer. So the reconciler is *level-triggered*: it compares the whole state on every pass, and events only make the next pass come sooner.

## Targets

Each thing Coffer keeps true is a **target**. The targets come from the agents' projection registry (see [Agent facets](/architecture/agent-facets)): for every agent, the assets it can receive — the MCP entry, skill links, a provider projection, a delivery hook. A target answers three questions and performs one kind of write:

1. **What should be there?** Computed only from Coffer's own state — its rows, each resource's reach, the running build's commands, where the launcher is — as a list of items, each with a stable key and every parameter it should have.
2. **What is there?** Read from the files and parsed into exactly the same shape, so the two can be compared directly. Parsing matters: several of these files are rewritten wholesale by their owners, so text comparison would see differences that mean nothing.
3. **What may be done about a difference?** The target's **direction policy** (below).
4. **The write.** Through the kind's own writer, which only ever touches Coffer's marked entry, writes atomically and keeps a backup of what was there.

A pass pairs the wanted and found items by key. A wanted item that is missing is an *addition*; a found item nothing wants is a *removal*; an item that is there with any parameter different is a *modification* — which is the case presence-based checks could never see.

## Direction policy

Not every difference may be repaired by writing. Each target states, for each difference, whether to **repair** it, only **report** it, or report it as **blocked** — repairable in principle but not right now. A difference the policy does not repair is reported, never written.

The policies encode judgements that were made once, the hard way, and that the reconciler keeps explicit:

- **Never clobber foreign content.** A directory someone else put where a skill link belongs is reported, not replaced. A missing master folder cannot be re-delivered from.
- **Never re-route an agent on stale evidence.** If the agent's record says it runs on a provider connection but its settings carry none of that connection's keys, the record is what is corrected: the agent's connection is cleared and the agent keeps running on its own login. Writing the keys back would silently send someone's agent through a gateway they are not using. Coffer's keys found with no connection behind them are reported rather than removed, for the same reason.
- **Connecting is the person's act.** Coffer never adds its MCP entry or its memory hook to an agent that has none; it only keeps an existing one current. A connected agent that lacks its hook is reported as partly connected.
- **Some warrants are stronger than others.** A few differences are repairable on one occasion and only reportable on another. After a sync import, the imported rows carry the person's explicit switch made on another machine, so a projection is written (or removed) to follow it. When a person applies an item from the drift view, they have asked for exactly that write. So a pass knows *why* it runs, and a policy may read that.
- **Blocked until the cause is gone.** When the launcher that an MCP entry must point at cannot be found, there is no correct entry to write, so the difference is reported as blocked; the same goes for a file that does not parse.

## When a pass runs

- **At start**, before the daemon reports ready — this is what repairs everything that drifted while it was down.
- **On a period** of one minute. A full pass over two connected agents, twenty delivered skills and an active provider was measured at under thirty milliseconds, so the period is set by how long drift may stand unnoticed, not by cost. A pass slower than two seconds is logged, because it would mean a target is doing too much.
- **Early, after a write.** Every write to a resource row, from any surface, announces the kind, the resource and its new revision — an integer every write increases. The announcement wakes the loop, which waits half a second for neighbouring writes and then runs a pass for the targets that follow that kind. The announcement is only an accelerator: if one is lost, the change is still found by the next periodic pass.
- **At once, for the person's own write.** When someone enables a skill, narrows its reach, imports it, or registers or moves an agent, the skill targets are reconciled before the request answers, so the change is visible immediately rather than a moment later.
- **For a sync import**, and for an [experimental feature](/guides/experimental-features) being switched, with the warrant each carries.

Passes never overlap. Some operations are several writes in a row — a provider switch writes the projection and then the agent's record; a sync round checks out many files, each of which hints, and then asks for its own import pass — and a pass that looked in between would see a half-done state and "repair" it back. Such an operation *holds* the reconciler while it runs: every other pass waits, and the passes it asks for itself run inside the hold. A repair that goes through such an operation does not wait on itself, because a hold taken from inside a pass holds nothing more.

A target that fails while being read is reported and skipped; the other targets are still reconciled. A write that fails fails only its own item, and the next pass tries again.

After a pass, what is derived from the agents' files is brought up to date: the [model proxy](/architecture/model-proxy) is pushed its state and the Overview's attention list is recomputed. A periodic pass that wrote nothing, failed no new target and left the same differences open skips this, because nothing those two read has changed; it is the common case on an idle daemon, once a minute.

## Preview without writing

The same pass can run as a **dry-run**: it computes exactly the plan a real pass would carry out and writes nothing — no file, no database row, no audit entry, not even an announcement. This is what the drift view and a change preview read: for each item the operation, the file, what is there and what would be written (rendered so that no secret value ever appears), and what the policy says. Because it is the same computation, what the preview shows is what a pass does.

## Audit follows the write

Every repair leaves an audit entry, and the entry is recorded in the same step as the write, before the pass moves on — with Coffer's automatic identity for a pass it ran itself, the sync identity for an import's pass, and the person's own for items they applied. The file and the audit log live in different stores, so there is no transaction that spans both, and none is claimed. Instead the order is fixed: write the file (keeping its backup), then record the entry. If the entry cannot be recorded, the file is put back to what the backup holds — or removed, if the write created it — and the item is reported as failed, so the next pass retries it. A crash exactly between the two leaves one unaudited write, which the daemon log records.

## What needs you

Drift the reconciler cannot fix on its own is one of several things that need a person. The Overview's **attention list** gathers them across every kind: drift that is reported or blocked, or that a pass tried and failed to repair; MCP servers whose last test failed, whose launcher is missing or whose secret is absent; agents whose program is missing or whose connection is partial; a sync stopped on a conflict, holding deletions for confirmation, refused by the remote or stopped by a plaintext secret; secrets with no value on this machine or waiting for approval, and the approval requirement while it is switched off; commands a skill requires or Coffer itself runs that are missing, outdated or logged out, and skills missing a secret they require; vault files whose hand edit validation refused; channels that are reconnecting, disconnected or not running; model providers an agent runs on whose endpoint does not answer or refuses the key. A kind contributes its own signals; a signal that belongs to an experimental feature appears only while that feature is switched on.

Each item says what it concerns, why (a stable code and one sentence), how urgent it is, when it was first seen where that is known, and exactly **one action** — the same request the kind's own page makes for it. The list therefore has no write of its own. A source that fails is shown as failed beside the others' items rather than hiding them. Signals nothing records yet — Telegram refusing a bot token — are not guessed at; a new source is how they will join.

## Adding a target

A new asset type for agents is a new entry in the projection registry and a new target beside it. The target states its items with every parameter, reads the same shape, writes through its kind's marked, atomic, backed-up writer, and declares its policy — including which triggers, if any, give it a stronger warrant. The tests that come with it are the same for every target: a changed parameter is found and repaired, what the policy withholds is reported and left untouched, a dry-run writes nothing, and a repair whose audit fails is put back.
