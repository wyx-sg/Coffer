# A Resource's Secret Is Named After the Resource and Its Slot, and Moves When the Resource Is Renamed

**Status**: Accepted
**Date**: 2026-10-04
**Deciders**: Yuxing Wu
**Related**: [Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), spec secret "Name a resource's secret after the resource and its slot"

## Context

A resource cites its secrets by ref ([credential-references](credential-references.md)).
The store gives a ref no meaning, so what a ref is called is a choice about the
people and tools that read it: the Secrets page's Copy reference and Used by
note, `coffer secret list`, the vault's `secret/<ref>.enc` files, the audit log
and a diagnostics bundle.

Refs were minted as `<kind>/<uuid4 hex>/<slot>` so that a rename would never
move a secret. In real use that produced
`mcp_server/643784232a6652abbf02c0f6aaf4a904/CONFLUENCE_PERSONAL_TOKEN` and
`provider/9c…/key`, beside older shapes (`postman.AUTHORIZATION`,
`agnes-apihub`) — a list nobody could read without opening each citer. The
user's report on 2026-10-04 was exactly that: the names mean nothing.

Two facts changed since the uuid shape was chosen: MCP server names became
fixed ([names-visible-to-agents-are-fixed](names-visible-to-agents-are-fixed.md)),
and only `channel` and `provider` — of the kinds that own secrets — can still be
renamed.

## Options Considered

### Option A — `<kind>/<name>/<slot>`, moved with a rename (chosen)

A secret a resource owns (it is the only citer, in one slot) is named after the
resource and the slot it fills: `mcp_server/confluence/CONFLUENCE_PERSONAL_TOKEN`,
`channel/seatalk/app-secret`, `provider/agnes/key`. Renaming a channel or a
provider moves the secrets it owns: write under the new ref, read back, repoint
the config through the resource service, carry this machine's binding and
timestamps, delete the old ref. The daemon applies the same move at start to
any owned secret not yet named this way, which also normalises a vault synced
from an older build. Shared refs and standalone `secret/<name>` are never
moved — their citers include files Coffer cannot rewrite.

Pros: every ref says whose secret it is; MCP servers, the most common owners,
never rename, so their refs never move; one mover serves rename and start-up.

Cons: a channel or provider rename now touches the store and crosses sync as a
rename of a `.enc` file; another machine with approvals on asks once more for
the moved ref, since bindings are per machine.

It wins because the ref is read far more often than a channel or provider is
renamed, and the move is one well-defined operation.

### Option B — `<kind>/<uuid4 hex>/<slot>` (the previous design)

Pros: a ref never moves; rename touches no secret.

Cons: unreadable everywhere a ref is shown; the slot is the only legible part,
and two servers' `AUTHORIZATION` cannot be told apart.

Lost: it optimises for the rare event (rename) at the cost of the common one
(reading).

### Option C — `<kind>/<name>/<slot>`, frozen at creation

Pros: readable at creation; no move on rename.

Cons: after a rename the ref names a resource that no longer exists under that
name — worse than an opaque id, because it is confidently wrong.

### Option D — `<kind>/<uid>/<slot>`

Pros: stable across rename; one secret per resource is easy to find from the
resource.

Cons: the uid is as unreadable as a fresh uuid; it fixes nothing the user
reported.

## Decision

Option A. The naming rule lives in `domain/secrets.py` and is mirrored in the
frontend's `lib/secretRef.ts`; the mover lives in `application/secret/`.
