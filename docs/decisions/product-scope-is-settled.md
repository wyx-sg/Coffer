# Product Scope Is Settled

**Status**: Accepted
**Date**: 2026-09-14
**Deciders**: Yuxing Wu (project owner)
**Related**: [`docs/principles.md`](../principles.md) (Principle I's user-owned sync remote exception); [The Desktop Shell Returns](desktop-shell-over-a-shared-frontend.md), [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md), [Vault Sync](vault-sync.md), [Knowledge Is Plain Files](knowledge-is-plain-files.md), [Aggregate Agent Memory](aggregate-agent-memory-never-write-it.md); specs [mcp-gateway](../../openspec/specs/mcp-gateway/spec.md), [channels](../../openspec/specs/channels/spec.md), [vault-sync](../../openspec/specs/vault-sync/spec.md), [web-ui](../../openspec/specs/web-ui/spec.md), [knowledge](../../openspec/specs/knowledge/spec.md), [memory](../../openspec/specs/memory/spec.md)

## Context

Between 2026-09-09 and 2026-09-14 the project removed five capabilities and
then put every one of them back:

| Capability | Removed | Restored |
| --- | --- | --- |
| Desktop shell | retired, the daemon serves the web UI (#317, 2026-09-09) | restored over the shared frontend (#376, 2026-09-13) |
| Web Chat page | removed, folded into the channels spec (#322, 2026-09-10) | brought back with its REST/SSE surface (#370, 2026-09-12) |
| Vault sync | continuous sync downgraded to export/import (#314, 2026-09-09) | one-way git backup (#362, 2026-09-12), then bidirectional convergence (#381, 2026-09-14) |
| Memory layer | merged into knowledge as one kind (#321, 2026-09-10) | split back out as its own kind (#379, 2026-09-13) |
| Activity page | audit reduced to a subset of events and one reader (#325, #331, 2026-09-10) | the three records Coffer keeps, each with its own tab (#377, 2026-09-13) |

Retrieval followed the same arc inside one day: ranked semantic search over an
embedding sidecar was removed with the knowledge reduction (#368, 2026-09-12),
restored the same day, and removed again (#382, 2026-09-14).

Each reversal was paid for twice. The project principles were amended three times in
five days (the first amendment removed the sync exception, the second added a
narrower one, the third replaced it). Migrations rewrote user data on the way out and on the way back
(`0066` dropped eleven knowledge tables, `0076` and `0077` cleaned up after the
reach and embedding changes). ADRs were deleted and re-created, spec sections
were cut and rewritten, and the roadmap's status cells grew into
multi-thousand-character amendment logs because every entry had to explain the
last reversal before it could state the current state.

The pattern behind every removal was the same: the capability was judged on
its maintenance cost alone, without weighing the reason it had been built —
and real use surfaced that reason within days. The shell was retired for the
cost of every update and restored for the cost of access; the Chat page was
removed because every conversation came from a channel and restored because
watching a phone-driven conversation from a desk is what no channel does; sync
was downgraded to avoid convergence machinery and restored because two machines
producing one vault is the product.

The one removal that is *not* in that list — semantic retrieval — was made for
a different reason and needs saying separately, because
[Knowledge Is Plain Files](knowledge-is-plain-files.md) records its cost so
carefully that a reader could take the removal as final.

## Decision

**Five capabilities are settled product scope.** They are not candidates for
removal, and a proposal to remove one is a proposal to amend this ADR, decided
by the project owner:

1. **The desktop shell** — spec [desktop-app](../../openspec/specs/desktop-app/spec.md),
   [The Desktop Shell Returns](desktop-shell-over-a-shared-frontend.md).
2. **The web Chat page** — the Chat page requirements of spec [chat](../../openspec/specs/chat/spec.md),
   [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md).
3. **Bidirectional vault sync with a user-owned remote** — spec vault-sync,
   [Vault Sync](vault-sync.md), Principle I's user-owned sync remote exception
   in `docs/principles.md`.
4. **The Activity page** — the audit log, the MCP invocation log and the
   daemon log, each with its own tab (spec web-ui; the records themselves
   are spec mcp-gateway's).
5. **The knowledge layer and the memory layer, as two kinds** — specs
   knowledge and memory, [Knowledge Is Plain Files](knowledge-is-plain-files.md),
   [Aggregate Agent Memory](aggregate-agent-memory-never-write-it.md).

**Literal retrieval is a placeholder, not a verdict.** Memory recall (and
knowledge's curation candidate selection — knowledge itself has no search
surface; agents read its files with their own tools) is the simplest thing
that answers — ripgrep where the machine has it,
a built-in Python walk with identical semantics where it does not — because the
knowledge and memory *design* is not yet settled, and an index built on an
unsettled design is what the 2026-09-12 audit found unused. Semantic retrieval
(embeddings, ranking) is expected to return once that design settles, under the
constraints Knowledge Is Plain Files already fixed: the files stay the only
truth, and any index is a disposable sidecar outside the vault. Nothing in this
repository is to be read as "we decided against semantic search".

**Removing a capability states its reversal cost.** A PR that removes any
capability — the five above by amendment, any other by ordinary review — MUST
state in its description what a reversal would cost: the code it deletes, the
migrations it runs against user data and whether they can be undone, and the
documents it rewrites (specs, ADRs, `docs/principles.md`, OpenSpec changes). It MUST remove the
dead code and every documentation reference in the same PR, so the tree never
carries a half-removed capability that the next reader has to reconstruct.

## Consequences

- The five capabilities' ADRs stay `Accepted` and their specs stay in
  `openspec/specs/`. Their maintenance cost — the Rust shell, the sync
  worker and its guards, two retrieval surfaces, three log readers — is
  accepted as the cost of the product, not a debt to be repaid by deletion.
- Specs describe the current state only; the history of how a capability
  changed lives in the archived OpenSpec changes (`openspec/changes/archive/`).
  A spec that starts explaining a reversal is the smell this ADR exists to
  stop.
- When semantic retrieval returns it re-enters through the knowledge and
  memory specs — a new requirement, not a new ADR — and the literal search stays as the
  fallback that answers while the index is missing, exactly as the 2026-09-12
  restoration had it.
- A removal PR without a stated reversal cost is incomplete and is sent back,
  the same way a PR that leaves its spec claiming the removed behaviour is.

## Alternatives Considered

- **Keep deciding per PR.** Rejected: that is the process that produced six
  reversals in six days. Each PR argued well from the cost it could see.
- **Feature flags for contested capabilities.** Rejected, and already rejected
  by the first of those principles amendments for the same reason: a flagged-off path still has to be
  maintained and tested, and a capability nobody can reach is not product
  scope, it is dead code with a switch.
- **Declare semantic retrieval permanently out.** Rejected: the 2026-09-14
  removal recorded a real loss — a query in the caller's own words no longer
  finds what a distinctive phrase would — and the reason it lost was the
  unsettled design under it, not the idea. A verdict made before the design is
  settled would be the same mistake as the five above, one level down.
