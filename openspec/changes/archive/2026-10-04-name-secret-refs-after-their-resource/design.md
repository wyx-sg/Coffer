## Decisions

- **Canonical ref** `<kind>/<name>/<slot>`. `name` is the resource's name with
  every character outside `[A-Za-z0-9_.-]` turned into `-` (a ref segment's
  alphabet); `slot` is the env var or header name (`mcp_server`), `bot-token`,
  `app-secret`, `signing-secret`, `tunnel-token` (`channel`), `key`
  (`provider`). One function in `domain/secrets.py` builds it; the frontend
  mirrors it in `lib/secretRef.ts`. If the canonical ref is already held by a
  ref something else cites, the name segment takes `-2`, `-3`, …
- **Owned vs shared.** A ref is the resource's own when that resource is its
  only citer, in one slot. Only owned refs are moved; a ref cited twice (a
  user pointing two servers at one token) is shared and keeps its name, as
  does every standalone `secret/<name>` (files Coffer cannot see cite it).
- **Move = copy, repoint, delete.** Write the value at the new ref and read it
  back; change the citing config through the resource service (validated,
  audited, reconciled); move this machine's bindings, creation time and
  last-used stamp from the old ref to the new; delete the old ref. A failure
  before the config changes deletes the new ref and leaves everything as it
  was.
- **Rename.** `channel` and `provider` rename hooks move the refs whose name
  segment is the old name; `mcp_server` names are fixed.
- **Startup.** The same mover runs once per daemon start over every owned,
  non-canonical ref; it is idempotent (a canonical ref is left alone), so a
  vault synced from a machine on an older build is normalised when it arrives.

## Risks

- Another machine receives the moved files and configs by sync but keeps
  bindings under the old ref names: with approvals on, it asks once again for
  each moved ref. Approvals are per machine by design; the cost is one
  confirmation.
- Sync carries a move as a delete plus an add; the sync deletion guard reads
  git's rename detection, so a moved `.enc` with the same content is a rename,
  not a loss.
