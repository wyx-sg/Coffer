# Coffer Constitution

> Coffer is a local-first AI agent vault: a developer's accumulated AI assets
> live on-device, and any AI agent (Claude Code, Codex, future ones) reads
> and contributes through one safe interface.
>
> This constitution holds **scaffolding-level** invariants only: tech stack,
> workflow, licensing posture, and architectural style. Product behavior —
> the resource model, the gate on who may drive an agent, the surface roster,
> what gets persisted where — is defined per feature in `specs/`.

## Core Principles

### I. Local-First (NON-NEGOTIABLE)

All user data lives on the user's machines — one vault, every machine holding
the full state. Cloud services are LLM and tool providers only — they never
become the system of record for any vault state. The HTTP API binds to
`127.0.0.1`. Replicating user-state to a vendor-controlled cloud requires a
constitutional amendment.

**Exception — user-owned sync remote.** Coffer may converge the vault with a
git remote the user owns, so that the user's own machines hold one vault rather
than several. The exception is bounded by three conditions, all of which must
hold: the remote is a **rendezvous, never a system of record** — each machine's
local vault stays authoritative and complete, so the remote can be deleted and
rebuilt from any single machine without losing anything; secrets travel **as
ciphertext only** and the master key never leaves the machine except through the
out-of-band key transfer; and the feature is **off by default**, enabled by the
user against a repository they own. A hosted endpoint Coffer itself operates
remains outside this exception.

Convergence is **bidirectional**: Coffer applies what the remote brought in as
well as pushing what this machine changed. It is authorised only under the
safety rules the sync spec carries — git's own three-way merge is the arbiter,
what gets applied is a **diff against the last state this vault provably held**
rather than a wholesale overwrite, and a round that would delete more than its
configured share stops and asks. A mechanism that writes the vault outside those
rules is not covered by this exception.

### II. Spec-as-Truth (Spec-Driven Development)

Specifications under `specs/` are the canonical product contract. Every PR
that changes externally visible behavior updates the relevant spec **first**,
then the code. A spec is not "documentation" — it is the implementation's
contract; if the code disagrees with the spec, the code is wrong.

### III. Open-Source-Readiness from Day One

License (MIT), governance, contribution flow, and Conventional Commits are
present in the repository from v0.0.1, not retrofitted later. A change that
would shorten this list — adding a closed-source dependency without an
exception, omitting attribution for AI-authored content — violates this
principle and requires a constitutional amendment with explicit migration
plan.

## Technology & Architectural Constraints

- **Languages.** Python 3.12+ for backend, CLI, and any MCP shim;
  TypeScript 5.x for frontend. No other primary languages without a
  constitutional amendment.
- **Architecture.** Layered: `surfaces → application → domain`;
  `infrastructure` adapts to ports defined in `application` and is wired only
  at the composition root.
  `domain/` may not import `infrastructure/`, `surfaces/`, or external SDKs.
  `application/` may not import `surfaces/`. Cross-cutting modules are
  extracted only after the second feature needs them. (Exception: the
  Resource framework — see [Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md).)
- **Persistence.** SQLite is the system of record for control-plane state.
  Bulk user content — knowledge collections, memory partitions — is stored as
  files on the local file system, and those files are the only copy: nothing
  indexes, chunks or embeds them.
- **Credentials.** Secrets live **only** as Fernet ciphertext in the
  `credentials` table; plaintext exists in memory solely between decrypt and
  the spawn/header-injection that consumes it. The Fernet master key is
  managed exclusively by `coffer.infrastructure.credentials` — a `0600` file
  beside the DB by default, the OS keychain via `keyring` when opted in.
  `keyring` import stays confined to that module. All other code uses
  credential refs. No secret plaintext reaches the database, logs, audit, or
  any structured event. Credential material leaves the machine only as Fernet
  ciphertext and only when the user asks for it explicitly; the master key is
  never written into anything the vault publishes, and reaches another machine
  only through the explicit out-of-band transfer (`/sync/key/export` and
  `/sync/key/import`, which move key material and nothing else).
- **Network defaults.** Loopback-only. Outbound HTTP goes through a
  SSRF-guarded client (`coffer.infrastructure.net.ssrf_guard`, which rejects
  loopback, private and link-local destinations). The one public-reachable
  surface runs as a separate process limited to signed callback paths
  (`coffer.surfaces.callback`, which verifies the platform signature and can
  reach nothing but the daemon over loopback).

## Quality Gates

A change is "done" only when **all** of the following hold:

- The relevant `spec.md` is updated to match the code.
- Acceptance scenarios in `spec.md` cover the new behavior and pass.
- `make verify` passes locally and in CI.
- File-size limits hold (see `agents/stack.md`).
- Architectural boundaries are not violated.

## Governance

This constitution **supersedes** any conflicting guidance in `AGENTS.md`,
`CONTRIBUTING.md`, or per-spec documents. When they disagree, the constitution
wins.

**Amendments.** A change to any Core Principle, to the Technology &
Architectural Constraints, or to a Quality Gate requires:

1. A proposal PR describing motivation, current behavior, proposed behavior,
   downstream impact, alternatives.
2. Explicit decision recorded in the PR description.
3. The amending PR updates this file and bumps the **Version** field below.

**PR review.** Every PR description must, where applicable, name the
constitutional principles or constraints it affects, and explain why the
change respects (or formally amends) them.

**Version**: 0.6.2

> **0.6.2 amendment (editorial).** Brought four sentences level with the code
> they describe; no rule changes. Motivation: each of them described something
> as unbuilt or hedged that has since shipped, or described a mechanism that has
> since been removed, so a reader learned the wrong thing about a constraint
> that was itself still correct. (1) The preamble listed "safety/approval rules"
> among per-feature product behaviour, which reads as a per-tool approval
> system; that system was removed and owner-pairing is the only gate
> ([Remove the Tool-Approval System](../../docs/decisions/remove-tool-approval.md)),
> so the phrase is now "the gate on who may drive an agent". (2) The Persistence
> constraint said bulk user content is stored as files "(when introduced per
> spec)" and "indexed on demand"; it is introduced, and the index is gone — the
> files are the only copy and nothing indexes, chunks or embeds them
> ([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)).
> (3) The Credentials constraint said the master key "is never written into an
> export"; export and import were deleted, and key material now moves only
> through `/sync/key/export` and `/sync/key/import`, which carry the key and
> nothing else. (4) The Network defaults constraint hedged outbound HTTP and
> public-reachable surfaces as "when introduced"; both exist —
> `infrastructure/net/ssrf_guard.py` and the `surfaces/callback` listener — so
> the hedges are removed and each rule names what implements it. Downstream
> impact: none — every constraint binds exactly what it bound before. Decision
> recorded by the project owner.

> **0.6.1 amendment (editorial).** Reworded the layering line of the
> Architecture constraint. Motivation: it wrote the layers as
> `surfaces → application → domain → infrastructure`, which reads as `domain`
> importing `infrastructure` — the one edge the very next sentence forbids, and
> the opposite of what [`agents/stack.md`](../../agents/stack.md) states
> ("`infrastructure` adapts to ports defined in `application`") and of what the
> import-linter contracts enforce (Contract 3: `domain` imports nothing;
> Contract 2b: `application` does not import `infrastructure`). Current
> wording: "Layered: `surfaces → application → domain → infrastructure`."
> Proposed wording: "Layered: `surfaces → application → domain`;
> `infrastructure` adapts to ports defined in `application` and is wired only
> at the composition root." Downstream impact: none — editorial; no import rule
> changes, and the contracts already enforce the corrected direction. Decision
> recorded by the project owner.

> **0.6.0 amendment (spec vault-sync — bidirectional sync).** Replaced the
> 0.5.0 *user-owned backup remote* exception with a *user-owned sync remote*
> exception, and with it restored the machine dimension 0.4.0 removed.
> Motivation: the user works the same project from two machines, and both
> produce vault state — knowledge files, skills, MCP registrations, agent
> configuration, credentials. One-way backup answers "my disk died"; it does not
> answer "both machines should see one vault", and export/import answers it only
> by hand. Current behaviour: Coffer pushes exports to a remote it never reads
> back, and a bundle is carried between machines by the user. Proposed
> behaviour: a background worker converges this machine with the remote — it
> commits what this vault holds, lets git three-way-merge it against what the
> remote holds, and applies the resulting difference back into the vault,
> deletions included. Downstream impact: spec vault-sync becomes Vault Sync; the
> local export/import commands, routes and UI are **deleted**, because "import a
> directory" is a wholesale overwrite with no base — the unsafe operation that
> caused the 2026-07-10 mutual-deletion incident — and it has no place beside the
> diff-based one; resource `scope` regains a machine axis; a machine registry
> returns as a **derived view** (each machine writes one file it alone owns, so
> the registry cannot conflict) rather than the synced table 0.4.0 deleted; a
> Sync page joins the top-level navigation.
>
> Principle I's opening line is reworded to the multi-machine reality again —
> the same sentence 0.3.1 wrote and 0.4.0 reverted — because a vault that
> converges across machines is no longer described by "the user's machine".
>
> **Why the machinery 0.4.0 priced is now affordable.** That amendment removed
> the exception because convergence required machine identity, tombstones with a
> TTL, conflict arbitration, quarantine-and-retry, a git workspace and a
> background worker. Two of those — the workspace and the worker — 0.5.0 has
> since built and paid for. The other four were expensive because the vault's
> bulk content was a **database** being projected into files, so the diff git saw
> was not the diff the vault made, and every guarantee had to be re-established
> outside git. Since [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)
> the bulk content **is** the files, and what remains in SQLite is a few dozen
> small deterministic documents. So tombstones disappear into git's own tree,
> machine identity collapses to one local pointer at the last converged commit,
> arbitration collapses into `git merge`, and quarantine collapses into a set of
> paths the exporter must not delete.
>
> **What the three surviving conditions cost.** *Rendezvous, not system of
> record* is enforced by the vault remaining complete on every machine: the
> remote holds nothing that is not also local. *Ciphertext only* is unchanged
> from 0.4.0's Credentials constraint. *Off by default* is unchanged from 0.5.0.
> The condition that goes is **one-way**, and only that one.
>
> Alternatives considered: **leaving the file trees to the user's own git and
> syncing only the structured state** — rejected, because Coffer running the pull
> is convergence either way and needs this same amendment, while the user running
> it means Coffer is not syncing at all; it also cuts the seam through `skill`,
> whose 220 files and 16 registry rows are two faces of one thing. **Restoring
> the 0.3.0 machinery as it was** — rejected, because it was built to converge a
> database that no longer exists. Decision recorded by the project owner.

> **0.5.0 amendment (spec vault-sync — backup remote).** Added the
> *user-owned backup remote* exception to Principle I. Motivation: export and
> import answer "move my vault to another machine", but they do not answer
> "my disk died" or "I deleted that skill last week" — both need a copy that
> lives somewhere the machine's own failure cannot reach, and a history deep
> enough to reach back past the moment of the mistake. Current behaviour: an
> export is local file output only; carrying it anywhere is the user's
> business. Proposed behaviour: Coffer may commit exports to a git repository
> and push them to a remote the user owns, on a timer, with restore as an
> explicit command. Downstream impact: spec vault-sync gains a backup
> remote, a scheduled push worker and a restore path; `sync_remotes` config and
> a git adapter join the sync slice. **This does not restore the 0.3.0
> exception**: that one authorised continuous convergence between machines, and
> the machinery 0.4.0 removed with it — machine identity, tombstones with TTL,
> conflict arbitration, quarantine-and-retry — stays removed and unauthorised.
> Backup is one-way, so none of it is needed. Alternatives considered:
> committing to a local git repository only and leaving the push to the user —
> rejected, because a local-only copy does not survive the disk failure the
> feature exists to survive. Decision recorded by the project owner.

> **0.4.0 amendment (spec vault-sync scope reduction).** Removed the
> *user-controlled sync medium* exception from Principle I and reverted the
> 0.3.1 wording of its opening line. Motivation: continuous multi-machine sync
> over a git remote carried the machinery its guarantees required — machine
> identity, tombstones with TTL, conflict arbitration, quarantine-and-retry, a
> git workspace and a background worker — and that cost was not repaid by the
> way the vault is actually moved between machines. Current behaviour: vault
> state syncs continuously to a user-owned git repository under the three
> conditions of the 0.3.0 exception. Proposed behaviour: Coffer exports the
> vault to a user-chosen directory and imports one back; no transport medium,
> no remote, no background replication, and therefore no exception to
> Principle I to maintain. Downstream impact: spec vault-sync narrows to export and
> import; the machine registry, the fleet view and the framework's machine
> scope axis go with it; the ciphertext-only rule the exception carried moves
> into the Credentials constraint, where it applies to every export rather
> than only to sync. Alternatives considered: keeping continuous sync behind a
> feature flag — rejected, because an unused code path still has to be
> maintained and tested. Decision recorded by the project owner.

> **0.3.0 amendment (spec vault-sync).** Added the *user-controlled sync medium*
> exception to Principle I, authorising multi-machine sync over a user-owned
> git repository under three conditions (no new system of record, ciphertext-
> only secrets, user opt-in/ownership). Motivation: enable a single user to
> keep one vault consistent across their own machines without ceding local-
> first guarantees. Current behaviour: multi-machine sync was an explicit
> non-goal. Proposed behaviour: permitted under the bounded exception above.
> Downstream impact: new spec vault-sync (sync engine, CLI/HTTP surfaces, daemon
> auto-sync worker); no change to credential-at-rest or loopback-binding rules.
> Alternatives considered: peer-to-peer (Syncthing-style) and user-owned object
> storage — rejected in favour of git for built-in history, diff, and merge.
> Decision recorded by the project owner.

> **0.3.1 amendment (editorial).** Reworded Principle I's opening line to
> match the multi-machine reality the 0.3.0 exception already authorised.
> Motivation: [Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)
> (then machine × agent resource scope) extends multi-machine
> sync further into the framework, underscoring that "local" has matured from
> a single machine into the user's fleet — one vault, every machine holding
> the full state — and the principle's opening sentence had not caught up.
> Current wording: "All user data lives on the user's machine." Proposed
> wording: "All user data lives on the user's machines — one vault, every
> machine holding the full state." Downstream impact: none — editorial;
> Principle I's rule and the 0.3.0 exception's three conditions are
> unchanged. Decision recorded by the project owner.
