# FR Ids Reset Once, Then Are Never Reused Again

**Status**: Accepted
**Date**: 2026-09-16
**Deciders**: Yuxing Wu
**Related**: [`.agents/sdd.md`](../../.agents/sdd.md), [Code Layout — Layer-First](code-layout-layer-first.md)

## Context

`.agents/sdd.md` has always said FR ids are **never reused**: a removed
requirement retires its number rather than handing it to the next one. The
reason is the same one that removed the numbers from ADR filenames and spec
directories — a reference to a deleted id is visibly dead, while a reference to
a recycled id is quietly wrong everywhere it is cited, in an ADR, a test marker,
a commit message.

The spec restructure carried out in this change breaks that rule on purpose, and
exactly once. It splits nine specs into fifteen top-level specs and four
children: content moves between specs, six new top-level specs (`chat`,
`credentials`, `daemon`, `desktop-app`, `internal-engine`,
`resource-framework`) and four children are created out of requirements that
lived in others, and two specs (`vault-sync`, `web-ui`) gain requirement ids for
the first time. After moves of that size, "never reused"
cannot be honoured *and* leave a readable numbering:

- A requirement that moves from `mcp-gateway` to `credentials` cannot keep
  `FR-011`, because the new spec's first requirement would then be number
  eleven with one through ten permanently absent.
- Numbers already retired in the old specs would be retired in specs that no
  longer exist.
- Keeping the old numbers while re-homing them means every new spec starts as a
  sparse, arbitrary set — the exact unreadability the rule exists to prevent.

The alternative to deciding this explicitly is worse than either option: the
next reader meets a spec whose ids were renumbered under a document that forbids
renumbering, and correctly reports it as a bug.

## Decision

**FR ids are reset once, in the restructure, and are never reused thereafter.**

Concretely:

1. In this change, every spec renumbers from `FR-001` in document order. This is
   the only such reset the repository will have.
2. From the moment the restructure lands, the original rule is back in force
   with no exception: a removed requirement retires its number, and the next
   requirement takes the next free one.
3. A future restructure does **not** inherit this licence. Moving a requirement
   between specs after this point gives it a fresh, next-free id in its new home
   and retires the old one; it does not trigger another global reset.

`.agents/sdd.md` states the rule in that form — "reset once, in the restructure;
never reused before or after" — so that the reset is discoverable from the
convention it appears to contradict.

## Consequences

- Every `FR-0NN` citation in the repository is rewritten in the same change:
  roughly 2,200 of them, most of which are bare and had to be resolved to a spec
  by context. They are rewritten from a reviewed old→new mapping table rather
  than mechanically, because a bare id means different requirements in different
  directories.
- Any reference to a Coffer FR id living **outside** this repository — an
  external note, a chat log, a memory file written before this change — is stale
  and cannot be mechanically detected. The mapping table is the only recovery
  path, so it is kept: see the restructure's commit message and
  [`.agents/sdd.md`](../../.agents/sdd.md).
- Git history before this change cites the old ids. `git log -S'FR-0NN'` reaches
  both eras and will mix them; date-bound the search at 2026-09-16.
- In exchange, every spec is readable from `FR-001` with no holes on day one,
  and the four new specs get numbering that matches their own document order
  rather than the order of the spec they were cut out of.

## Alternatives Considered

**Keep the old ids wherever a requirement lands.** Honours "never reused"
literally. Rejected: each new spec would open at an arbitrary number with
permanent gaps, and readers would have to know the pre-restructure specs to
understand why. The rule exists to protect citations, and this restructure
rewrites every citation anyway — so the protection buys nothing while the cost
is paid in full.

**Renumber only the specs that changed.** Rejected: "changed" covers all nine
(every one loses content, gains content, or is renamed), so it is the global
reset with a qualifier that reads as an exemption someone would later claim.

**Introduce globally unique FR ids so moves never renumber.** A real fix for the
underlying problem, and rejected as a much larger change than this one: it
invalidates the per-spec `FR-001` convention, every `<spec-id> FR-00N` citation
form, and the `scripts/audit_acceptance.py` marker vocabulary. Worth
reconsidering on its own if requirements move between specs often — they have
not, once, before this restructure.
