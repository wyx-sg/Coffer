# Coffer Ships Its Own Manual as a Skill Resource

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: spec skill-manager; spec knowledge; spec resource-framework; spec experimental-features; [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md); [Sync Withholds Derived Output](sync-withholds-derived-output.md); [Kind Plugin Contract](kind-plugin-contract.md); [Tool Overload: Tier the List, Search the Rest](tool-overload-tier-the-list-search-the-rest.md); research note [agent skills](../research/agent-skills.md); PR #405

## Context

An agent meets Coffer through a tool list and one paragraph. Everything else it
needs to work with Coffer well — that an upstream tool missing from the list is
still callable through `coffer__search_tools`, that knowledge is files it reads
with its own tools, which knowledge exists and where, that Coffer reads its
memory and never writes it, that no Coffer tool waits on a human approval — had
nowhere to live.

Two channels into a model's context have opposite cost structures:

- **The MCP `initialize` `instructions` field** is the only way a server
  reaches a client's system prompt, and it is paid in every session whether or
  not any of it is needed. Coffer caps it at 800 characters
  (`MAX_INSTRUCTIONS_CHARS`, `backend/coffer/application/mcp/gateway_instructions.py`).
  At that size it can say what Coffer is, name the built-in tools so they are
  recognisable, and state the one thing true only of *this* session — how many
  upstream tools were left out of the list. It cannot carry a manual, still less
  a catalogue of the user's knowledge.
- **A skill** has a frontmatter description that is resident in every session
  (about 160 tokens here) and a body that costs nothing until a model reaches
  for it.

The knowledge layer already delivered a generated skill with a catalogue, and
did it outside the resource framework: it wrote real bytes into each agent's
`<config_dir>/skills/` itself, on the grounds that a skill Resource is a bundle
a person imports and owns, and nobody can keep a bundle level with a catalogue
that curation rewrites. That delivery was invisible on the Skills page, beyond
the reach of `enabled` and scope, and outside drift verification, boot repair,
reclaim and the audit trail — two ways to put a folder in an agent's skills
directory, one of which nothing could see. And the 448-session audit behind
[Knowledge Is Plain Files](knowledge-is-plain-files.md) found that skill never
once loaded: its description named the layer, not the subjects.

## Options Considered

### Option A — One generated skill, `coffer-guide`, registered as an ordinary skill Resource (chosen)

The manual and the knowledge catalogue are one `SKILL.md`, regenerated from the
running build at every daemon boot and whenever the catalogue changes, written
into one master folder under `~/.coffer/skills/coffer-guide/` and registered as
a `skill` Resource whose source is `builtin`. It is delivered by the same
predicate and links as every imported skill.

- **Pros.** One delivery mechanism for all skills: Coffer's own is listed,
  scoped, enabled, delivered, verified for drift, repaired at boot, reclaimed
  and audited by the same code as the user's. A person who does not want it
  disables it where they disable anything else. The resident cost is paid once,
  on one description that can carry matchable specifics. The manual has room to
  grow at no per-session cost.
- **Cons.** The master folder is Coffer's to rewrite, so a person's edit to it
  is lost at the next boot. The prose can drift from the code with no compiler
  to catch it. The rendered text differs per machine, which a synced resource
  must be taught to tolerate.
- **Why it wins.** "Generated" and "registered" stopped being alternatives once
  the master is re-rendered in place: one write re-renders what every agent
  reads, and reclaiming one agent's link is the skill kind's own per-agent
  reconciliation.

### Option B — Several skills (tools, knowledge, memory)

- **Pros.** Each body is smaller and more focused.
- **Cons.** Every description is resident in every session, so a set pays the
  resident cost several times over to advertise things most sessions never
  open, and splits the matchable surface across descriptions a model must
  choose between.
- **Why it lost.** One description, one body is the cheapest way to be found.

### Option C — Handshake instructions only

Put everything in the `initialize` instructions.

- **Pros.** No skill machinery; guaranteed to be in context.
- **Cons.** Paid by every session in full. At 800 characters it cannot hold a
  manual; raising the cap trades a permanent per-session cost for material most
  sessions never need, and a catalogue of hundreds of documents cannot fit at
  any reasonable cap.
- **Why it lost.** The handshake keeps only what a skill cannot carry.

### Option D — A per-agent generated copy written outside the framework (the design this replaced)

The knowledge layer writes independent bytes into each agent's skills
directory itself.

- **Pros.** No person is asked to maintain a bundle; no link into a shared
  master.
- **Cons.** A second delivery mechanism with its own writer, invisible to
  every surface and to `enabled`, scope, drift verification, boot repair and
  audit.
- **Why it lost.** Its two objections — that a shared-master link could not be
  re-rendered or reclaimed — were answered by the skill kind itself (PR #405).

### Option E — A documentation file the agent is told about (`AGENTS.md`, a docs page)

- **Pros.** Plain prose; no generation.
- **Cons.** Something must still tell each session the file exists — which is
  the resident-description problem again, or a write into the agent's own
  instruction files, which Coffer does not do. A static page cannot carry the
  per-machine catalogue.
- **Why it lost.** A skill already is "a file plus a resident pointer to it",
  with a mechanism every supported agent loads.

### Option F — An MCP resource or prompt

Serve the manual through the MCP resources or prompts API.

- **Pros.** Stays inside the protocol Coffer already speaks; no files in the
  agent's directory.
- **Cons.** Nothing in either agent loads an MCP resource into context of its
  own accord; the model has to know to request it, which is the step the audit
  showed never happens. Skill descriptions, by contrast, are matched
  automatically.
- **Why it lost.** It reproduces the "tool nobody remembers to call" failure.

## Decision

**Coffer ships its own manual as a real `skill` Resource named `coffer-guide`,
and the knowledge catalogue is one section of it.**

- **One skill, one description, one body.** The description names Coffer, the
  built-in tools this machine has, and the subjects the enabled collections
  cover, within the tightest importer ceiling (1024 characters), dropping whole
  subjects from the tail rather than cutting a sentence. The body is the manual
  — the tools and when to reach for each, the tiering contract, that knowledge
  is files read with the agent's own tools, that Coffer never writes an agent's
  memory, that nothing waits on an approval — followed by the catalogue.
- **The tool count is conditional.** `coffer__diagnose` and
  `coffer__search_tools` are always present; `coffer__write` exists only while
  the `knowledge` experimental feature is on and `coffer__recall` only while
  `memory` is. The rendered manual drops the span belonging to a switched-off
  feature and states the tool count that remains
  (`backend/coffer/application/knowledge/guide_render.py`); the handshake names
  only the tools actually listed. Neither ever documents a tool the gateway
  would answer as unknown.
- **The handshake narrows to what only it can say.** What Coffer is, the listed
  built-in tool names, the per-session hidden-tool count when tools are hidden,
  and a pointer to the skill.
- **Generated, deterministic, and never received.** The master is rewritten
  from the build at every boot and whenever the catalogue moves; the same build
  over the same enabled collections renders the same bytes, so an unchanged
  catalogue writes, audits and delivers nothing. The `builtin` source variant
  carries no fields — nothing about where a generated folder came from will be
  true tomorrow. The folder and its row are derived output and do not travel
  between machines; why is argued in
  [Sync Withholds Derived Output](sync-withholds-derived-output.md).
- **Deletion is refused; reach is not.** `enabled` and `scope` stay the
  owner's. Deleting it is refused with `RESOURCE_PROTECTED` (409), naming
  disable and scope as what the owner wants, because the next boot would write
  it back.
- **The refusal is a framework seam.** `Kind.validate_delete`, a pre-write
  validator run after the resource is resolved and before the cleanup hook
  (`backend/coffer/domain/resource.py`), so the kind-agnostic
  `DELETE /api/v1/resources/{uid}` and `DELETE /api/v1/skills/{uid}` refuse
  identically. Refusing from inside `on_delete` would refuse after the
  framework had committed.

## Consequences

- **One delivery mechanism for skills again**, and Coffer's own skill inherits
  all of it.
- **The manual can grow for free** until a model opens it; the 800-character
  handshake no longer has to choose between useful and cheap.
- **The manual is prose that must be kept true.** A renamed tool or changed
  behaviour leaves a paragraph quietly wrong. The handshake is held against the
  registered tool names by a contract test; the skill body is not, and that gap
  is real.
- **Edits to the master do not survive a boot.** That is intended, and it is
  the kind of thing a person discovers at the worst moment, so every surface
  marks the skill as built-in and says what that means.
- **Enforcement.** Spec skill-manager "Regenerate Coffer's builtin skill from
  the build", spec skill-manager "Refuse deleting a builtin skill",
  spec skill-manager "Mark the builtin skill on every surface",
  spec knowledge "Deliver the catalogue through the coffer-guide skill",
  spec knowledge "Keep the handshake instructions to what a skill cannot carry",
  spec knowledge "Render the guide skill deterministically",
  spec experimental-features "Withdraw what a switched-off feature put in front of agents".
