## MODIFIED Requirements

### Requirement: Re-run post-import hooks after applying
After the diff is applied, each kind's post-import hook MUST re-apply its
machine-local side effects from current state. Everything the unified
reconciler converges — native config projections, Coffer's MCP entries, skill
deliveries, delivery hooks — is re-applied by one hook that runs a reconcile
pass with the import's warrant (see [resource-framework](../resource-framework/spec.md)
"Converge what Coffer writes outside its database with one reconciler"), and
the round MUST keep every other reconcile pass out from the start of its apply
until that pass is done, so no pass judges rows the round has half applied.
Each item the pass could not bring in step, and each target that failed, is
reported among the round's failures.

#### Scenario: a remote addition lands in the vault
- **GIVEN** a remote holding an `mcp_server` this vault does not have,
- **WHEN** a round runs,
- **THEN** the server is registered locally, its post-import hook has run, and
  the pointer advances past the commit that added it.
