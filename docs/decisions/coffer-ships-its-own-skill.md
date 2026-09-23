# Coffer Ships Its Own Manual as a Skill Resource

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: spec [skill-manager](../../openspec/specs/skill-manager/spec.md), spec [knowledge](../../openspec/specs/knowledge/spec.md), spec [resource-framework](../../openspec/specs/resource-framework/spec.md); [The knowledge layer is a directory of files, not an index](knowledge-is-plain-files.md) (whose "delivered as an independent copy per agent" clause this replaces); [Budget-Driven Tool Tiering at the Gateway](budget-driven-tool-tiering.md); [Vault Sync](vault-sync.md); [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md)

## Context

An agent meets Coffer through a tool list and one paragraph. Everything else it
would need to work with Coffer well — that an unlisted upstream tool is still
callable, that knowledge is files it reads itself, that Coffer never writes its
memory, that no Coffer tool is waiting on a human — had nowhere to live.

**What the handshake can carry, and what it cannot.** The MCP `initialize`
`instructions` field is the only channel a server has into a client's system
prompt, and it is charged against every session whether or not any of it is
needed. Coffer caps it at 800 characters for that reason. At 800 characters it
can say what Coffer is, name the tools so they are recognisable when they
appear, and say the one thing that is only true in *this* session — how many
upstream tools were left out of the list. It cannot carry a manual, and it
certainly cannot carry a catalogue of the user's knowledge. Every attempt to
make it do so was a trade of a permanent per-session cost against material most
sessions never need.

**A skill has exactly the opposite cost structure, which is also why it is one
skill and not a set.** A skill's frontmatter description is resident in every
session whether or not the skill is ever opened; its body costs nothing until a
model reaches for it. So the resident budget should be spent once, on the one
description a model can actually match against, and everything else belongs in
a single body behind it. A set of skills — one for tools, one for knowledge,
one for memory — would pay the resident cost several times over to advertise
things most sessions never open. One description, one body.

**Why the previous design kept the generated skill out of the resource
framework.** The knowledge layer already delivered a generated skill, and it did
so by writing bytes into each registered agent's own `<config_dir>/skills/`
directory itself. That was deliberate, and the reasoning was sound at the time:
a skill Resource is a bundle a *person* imports and then owns, and no person can
keep a bundle level with a catalogue that is rewritten every time curation runs.
Two further claims followed from it — that a link into a shared master would be
"a copy this layer cannot re-render, stale or reclaim", and therefore that each
agent must hold independent bytes.

What that bought was a folder nobody had to maintain. What it cost was a second
delivery mechanism living beside the first: its own writer, its own per-agent
copies, invisible on the Skills page, unreachable by `enabled` or by scope, and
outside every piece of machinery the skill kind already had — drift
verification, boot repair, reclaim, the audit trail. Two ways to put a folder in
an agent's skills directory, one of which nothing could see.

## Decision

**Coffer ships its own manual as a real `skill` Resource named `coffer-guide`,
and the generated knowledge skill is folded into it.** One master folder under
`~/.coffer/skills/coffer-guide/`, one resource row, delivered by the same
predicate and the same links as any imported skill.

- **One skill, one description, one body.** The description names Coffer, its
  four built-in tools, and the subjects the user's enabled collections cover.
  The body is the manual — the tools and when to reach for each, the tiering
  contract, that knowledge is files read with the agent's own tools, that Coffer
  reads an agent's memory and never writes it, that nothing waits on an approval
  — followed by the catalogue of every knowledge document with its path.
- **Generated is not the opposite of registered.** The master folder is
  rewritten from the running build at every daemon boot and whenever the
  catalogue moves. So the reason the knowledge skill stayed outside the
  framework is gone, and with it the case for independent per-agent bytes: the
  master is re-rendered in place, which re-renders what every agent reads in one
  write, and reclaiming one agent's copy is the skill kind's own per-agent
  reconciliation against the delivery predicate.
- **The `builtin` source variant carries no fields.** Not a path, not a
  timestamp, not a build id. There is nothing about where a generated folder
  came from that will still be true tomorrow, and anything stored would differ
  between machines (see Consequences).
- **Deletion is refused; reach is not.** `enabled` and `scope` stay entirely the
  owner's — those decide reach. Existence does not: the next boot writes the
  folder back, so a delete would read as destructive and behave as a no-op that
  had torn down some links on the way. It is refused with `RESOURCE_PROTECTED`
  (409), and the refusal names disable and scope as what the owner actually
  wants.
- **The refusal is a framework seam, not a route guard.** `Kind` gains an
  optional pre-write `validate_delete`, run after the resource is resolved and
  before the cleanup hook. It is a *validator* rather than a rejection from
  inside `on_delete`, because `on_delete` is a reaction to a delete that has
  already been decided — a kind refusing from in there refuses after the
  framework has committed. Placing it in the framework is what makes the
  kind-agnostic `DELETE /api/v1/resources/skill/{name}` and the skill kind's own
  route refuse identically; a guard written into one route is a guard the other
  silently lacks.
- **The handshake narrows to what only it can say.** What Coffer is, the four
  tool names, the per-session hidden-tool count, and a pointer to the skill.

## Consequences

**Easier.** There is one delivery mechanism for skills again, and Coffer's own
skill inherits all of it for free: it is listed, scoped, enabled, delivered,
verified for drift, repaired at boot and audited by the same code as the user's
own. A person who does not want it disables it, in the place they disable
anything else. And the manual now has somewhere to grow that costs a session
nothing until it is opened — the 800-character handshake no longer has to
choose between being useful and being cheap.

**The convergence hazard, and the rule that answers it.** A skill's master
folder and its resource row both travel between machines, while this particular
folder is regenerated *locally* at every boot. Those two facts together are a
trap: machine A's boot produces bytes that differ from machine B's, each vault
faithfully converges the other's version away, and the two overwrite each other
forever, each one correct and each one different. A conflict that never resolves
because nothing is wrong.

The first answer was determinism — forbid anything machine-specific in the
rendered file and the two machines render the same bytes. **That answer was not
enough, and the reason is worth being precise about.** Determinism can only
remove differences that are accidental, and the biggest input to this file is
not accidental at all: the catalogue is built from the collections that are
**enabled**, and `enabled` is reach, which vault-sync deliberately keeps
machine-local. A laptop that has switched a collection off is *supposed* to
render a shorter manual than the desktop. There is no rule about byte-order that
makes those two agree, because they are not meant to agree. Version skew does
the same thing on its own, since the shipped half of the text moves between
builds.

So the real answer is that **this artifact does not converge at all** — neither
its master folder nor its resource row (spec vault-sync FR-093). It is derived
output: every machine already holds everything it takes to produce its own, from
files that converge plus its own switches, so publishing it is pure churn. The
resource framework carries the rule the same way it carries `memory`'s, on the
kind rather than as a name in the sync layer — `skill` declares that a row whose
source is `builtin` is derived, while every skill a person imported keeps
travelling — and the mirrored `skills/` tree leaves that one folder alone in
both directions. Withholding it never publishes its *absence* either: a bundle
an older build wrote already carries those paths, and staging their deletion
would hand a machine still running that build an instruction to tear down its
own live copy (FR-094).

Determinism survives as a rule, with a smaller and more honest justification
(spec knowledge FR-047): an unchanged catalogue re-rendering to the same bytes
is what lets the seed skip the write, so a boot or a curation tick that changed
nothing registers nothing, audits nothing and re-delivers nothing. That is why
the knowledge root is still written in its `~`-relative form in its default
place — now because a path an agent reads should be one a person can retype —
and why the config records no timestamp of its generation.

**Harder.** The manual is now something to keep true. A tool renamed, a
behaviour changed, an approval story altered — each one has a paragraph
somewhere that will quietly start lying, and no compiler checks prose. The
handshake is held against the registered tool names by a contract test; the
skill body is not, and that gap is real.

**A trap this removes.** An edit to `~/.coffer/skills/coffer-guide/` does not
survive the next boot. That is the intended behaviour, and it is exactly the
kind of thing a person discovers at the worst moment, so the surfaces mark the
skill as built-in and say what the mark means rather than leaving it to be
found.
