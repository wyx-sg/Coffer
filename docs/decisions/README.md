# Architecture Decision Records (ADR)

Coffer records every major technical or architectural decision as an
ADR. ADRs capture **why** — code shows _what_, this directory shows
_why we chose what we chose_.

## When to write an ADR

Write one for any **technical** decision that meets at least one of these:

- Hard to change later without breaking compatibility or rewriting large areas.
- Affects more than one module, or imposes structural constraints on future work.
- Has non-obvious trade-offs that future engineers (or future you) will question.
- Diverges from a default, a popular convention, or a project rule
  (a clause of the [principles](../../docs-site/architecture/principles.md), a prior ADR).

Do **not** write an ADR for:

- Library version bumps that don't change API surface.
- Routine bug fixes.
- Product scope — what a capability does and does not do belongs in its spec's
  `## Purpose` or in the requirement that bounds it.
- Project process — how we branch, review or release belongs in `.agents/`.
- Naming or formatting preferences, and UI conventions (`.agents/frontend.md`).
- A survey of how other products solve a problem — that is a research note
  under [`docs/research/`](../research/README.md), which an ADR may cite.

## One technical point, every option argued

- **One decision per file.** If the Decision section needs "and also", it is two
  ADRs. A decision that only makes sense beside another links to it rather than
  absorbing it.
- **Every serious option is written out**, the chosen one included: how it
  would work, what it is good at, what it costs, and the concrete reason it won
  or lost. "Considered and rejected" with no reason is not an option. A reader
  who disagrees with the choice should find their preferred option already
  there, argued on its merits.
- **Evidence over assertion.** Where a choice rests on a measurement, a platform
  limit or an incident, name it (the number, the API doc, the PR).
- **Length follows the decision.** There is no line limit; there is a
  one-decision limit. Implementation detail that does not bear on the choice
  belongs in the code, the spec, or the architecture docs.

## File naming and lifecycle

- Filename: `short-kebab-case-title.md` — the title, in kebab case, with no
  number. Numbers were dropped because deleting an ADR left a hole in the
  sequence, and compacting those holes would have made every surviving
  reference to a retired number point silently at an unrelated live decision —
  which had already happened once. A name cannot do that, and chronology is
  carried by each ADR's own `Date`.
- This directory records the **live** design, not a chronological archive. A
  reader must be able to learn today's answer by reading the ADRs present, never
  by replaying a chain of supersessions. So:
  - When a decision changes, **rewrite the ADR that owns it** so it reads as if
    written today. The design it replaced becomes one of its options, argued
    like any other — not an `Amended` note, a struck-through line or a revision
    log.
  - When the thing an ADR decided is **removed outright**, delete the ADR.
  - Keep an ADR marked `Superseded by <title>` only when the superseded design
    still explains a constraint the live one inherits.
  Git history is the archive: `git log --follow docs/decisions/` recovers any
  decision this directory no longer states.

## Status values

| Status                  | Meaning                                             |
| ----------------------- | --------------------------------------------------- |
| `Proposed`              | Drafted, not yet adopted.                           |
| `Accepted`              | In effect.                                          |
| `Superseded by <title>` | No longer the live answer; link to its replacement. |
| `Deprecated`            | Withdrawn without replacement (rare).               |

## Template

```markdown
# <short title in title case — states the decision>

**Status**: Proposed | Accepted | Superseded by [<title>](<file>.md)
**Date**: YYYY-MM-DD (when the decision in its current form was taken)
**Deciders**: <names / roles>
**Related**: [<ADR title>](<file>.md), spec <capability>, research note, PR

## Context

<The problem and the forces on it: constraints, measurements, incidents,
the principles clause or neighbouring ADR it has to live with. Enough that a
reader could weigh the options below without having been there.>

## Options Considered

### Option A — <name> (chosen)

<How it works. Pros. Cons. Why it wins.>

### Option B — <name>

<How it works. Pros. Cons. The concrete reason it loses.>

<…every serious option, including the design this one replaced.>

## Decision

<The choice, stated as today's design in a few sentences, plus the rules it
implies that a future change must respect.>

## Consequences

<What becomes easier, what becomes harder, what obligations follow, and where
in the code or spec the decision is enforced.>
```

## Index

Grouped by area. Every ADR here is `Accepted` and states the live design.


### Resource framework & persistence

| ADR | Decision |
| --- | --- |
| [`resource-framework-upfront`](resource-framework-upfront.md) | The Resource Framework Is Core Domain, Designed Before the Second Kind |
| [`kind-plugin-contract`](kind-plugin-contract.md) | A Kind Plugs In as One Frozen Record of Optional Hooks: Validators Before the Write, Reactions After |
| [`resource-identity-is-an-immutable-uid`](resource-identity-is-an-immutable-uid.md) | Resource Identity Is an Immutable `uid`, Not the Name |
| [`per-agent-resource-scope`](per-agent-resource-scope.md) | Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind |
| [`resource-reach-is-machine-local`](resource-reach-is-machine-local.md) | Resource Reach Is Machine-Local and Never Converges |
| [`code-layout-layer-first`](code-layout-layer-first.md) | Code Layout Is Layer-First, With One Subdirectory per Kind |
| [`composition-root-explicit-wiring`](composition-root-explicit-wiring.md) | Kinds Are Wired Explicitly by One Composition Root, With No Global Registry |
| [`sqlite-alembic-persistence`](sqlite-alembic-persistence.md) | Control-Plane State Is One SQLite File, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage |
| [`audit-and-retention`](audit-and-retention.md) | Audit Every Change With Its Actor, Log Invocations Without Payloads, Prune Per Table |

### Daemon, shell & distribution

| ADR | Decision |
| --- | --- |
| [`daemon-detect-or-spawn`](daemon-detect-or-spawn.md) | Any Surface Finds the Daemon or Spawns It |
| [`daemon-binds-a-fixed-port`](daemon-binds-a-fixed-port.md) | The Daemon Binds a Fixed Port and Refuses to Start Without It |
| [`daemon-is-a-resident-login-service`](daemon-is-a-resident-login-service.md) | The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash |
| [`daemon-auth-and-origin-guard`](daemon-auth-and-origin-guard.md) | A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard |
| [`stdio-shim-bridge`](stdio-shim-bridge.md) | Agents Reach the Gateway Through a stdio Shim, Not a Native HTTP Entry |
| [`desktop-shell-over-a-shared-frontend`](desktop-shell-over-a-shared-frontend.md) | The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do |
| [`daemon-proxies-os-file-actions`](daemon-proxies-os-file-actions.md) | The Loopback Daemon Performs OS File Actions for the UI |
| [`distribution-pyinstaller`](distribution-pyinstaller.md) | Distribution — Three PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App |
| [`experimental-features-instead-of-a-release-branch`](experimental-features-instead-of-a-release-branch.md) | Experimental Features Instead of a Release Branch |
| [`sidebar-grouped-by-role`](sidebar-grouped-by-role.md) | The Sidebar Is Grouped by Role: Agents, Resources, System |

### MCP gateway

| ADR | Decision |
| --- | --- |
| [`session-subprocess-model`](session-subprocess-model.md) | One Upstream Subprocess Set Per Downstream Client Session |
| [`capability-state-model`](capability-state-model.md) | MCP Capability State — Preferences in the Database, Lists Live-Queried From Upstream |
| [`tool-overload-tier-the-list-search-the-rest`](tool-overload-tier-the-list-search-the-rest.md) | Tool Overload: List a Usage-Ranked Slice, Search the Rest |
| [`eval-capture-and-regression-gate`](eval-capture-and-regression-gate.md) | Evals: Opt-In Capture, Hand Curation, and a Deterministic Regression Gate |

### Agents, providers & the internal engine

| ADR | Decision |
| --- | --- |
| [`agent-descriptor-manifest`](agent-descriptor-manifest.md) | Per-Agent Behaviour Lives in One Descriptor Record per Agent |
| [`writing-agent-native-config-safely`](writing-agent-native-config-safely.md) | Writing Agent-Native Config Safely |
| [`agent-hook-installation`](agent-hook-installation.md) | Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale |
| [`provider-connections-projected-into-agent-config`](provider-connections-projected-into-agent-config.md) | LLM Connections Are Projected Into Each Agent's Own Config File |
| [`provider-keys-never-land-in-native-config`](provider-keys-never-land-in-native-config.md) | Provider Keys Never Land in an Agent's Native Config |
| [`model-catalogue-read-from-the-agent`](model-catalogue-read-from-the-agent.md) | The Model Catalogue Is Read Back From the Installed Agent |
| [`coffer-model-is-an-internal-engine`](coffer-model-is-an-internal-engine.md) | Coffer's Own Model Is an Internal Engine, Not a Persona or a Tool |
| [`internal-engine-settings`](internal-engine-settings.md) | The Engine Owns Its Model; Its Endpoint Is Borrowed From a Flagged Connection |

### Chat & channels

| ADR | Decision |
| --- | --- |
| [`driving-agents-through-sdk-and-app-server`](driving-agents-through-sdk-and-app-server.md) | Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server` |
| [`managed-agents-run-with-full-permissions`](managed-agents-run-with-full-permissions.md) | Managed Agents Run With Full Permissions; Owner Pairing Is the Gate |
| [`chat-single-owner-live-mirror`](chat-single-owner-live-mirror.md) | Chat Is a Single-Owner Live Mirror |
| [`channel-adapter-framework`](channel-adapter-framework.md) | Channels Are Thin Transport Adapters Over One Shared Core, Supervised In-Daemon |
| [`channel-owner-gate`](channel-owner-gate.md) | A Channel Answers Only Its Paired Owner, and Fails Closed in Groups |
| [`channel-conversation-identity-and-context`](channel-conversation-identity-and-context.md) | A Channel Conversation Is Keyed by (Channel, Chat, Thread) and Grounded in Its Thread and Quote |
| [`channel-switches-structural-vs-parametric`](channel-switches-structural-vs-parametric.md) | Channel Switches: the Agent Opens a New Conversation, Model and Effort Apply Next Turn |
| [`channel-live-surface-strategy`](channel-live-surface-strategy.md) | A Channel Reply Grows on One Live Surface, Paced by the Transport |
| [`channel-attachments`](channel-attachments.md) | Channel Attachments: Bytes on Disk, a Reference in the Message, Materialised per Agent at Send |
| [`seatalk-websocket-inbound`](seatalk-websocket-inbound.md) | SeaTalk Inbound Is One Outbound WebSocket, Through an Operator-Supplied SDK |
| [`telegram-long-polling`](telegram-long-polling.md) | Telegram Inbound Is a Long Poll That Commits the Offset After Dispatch |

### Skills, knowledge & memory

| ADR | Decision |
| --- | --- |
| [`cross-platform-skill-delivery`](cross-platform-skill-delivery.md) | Skills Reach an Agent as a Directory Link to One Master Folder |
| [`coffer-ships-its-own-skill`](coffer-ships-its-own-skill.md) | Coffer Ships Its Own Manual as a Skill Resource |
| [`knowledge-is-plain-files`](knowledge-is-plain-files.md) | Knowledge Is a Directory of Markdown Files, Not an Index |
| [`knowledge-curation`](knowledge-curation.md) | Knowledge Curation Merges New Material Into the Documents |
| [`aggregate-agent-memory-never-write-it`](aggregate-agent-memory-never-write-it.md) | Aggregate the Agents' Memory; Never Write It |

### Sync & credentials

| ADR | Decision |
| --- | --- |
| [`vault-sync`](vault-sync.md) | The Vault Converges With One User-Owned Git Remote, Git's Merge as Arbiter |
| [`sync-deletion-breaker`](sync-deletion-breaker.md) | A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves |
| [`sync-machine-identity`](sync-machine-identity.md) | A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree |
| [`single-owner-machine-for-unattended-rewrites`](single-owner-machine-for-unattended-rewrites.md) | An Unattended Rewriter of Synced Content Runs on One Named Owner Machine |
| [`sync-withholds-derived-output`](sync-withholds-derived-output.md) | Sync Withholds Derived Output; Each Machine Renders Its Own |
| [`envelope-encrypted-credential-store`](envelope-encrypted-credential-store.md) | Envelope-Encrypted Credential Store |
| [`credential-references`](credential-references.md) | Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use |
| [`credentials-across-machines`](credentials-across-machines.md) | Credentials Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository |
