## Why

Review of the drift decisions found five edges where the code or the spec said
less than the owner decided: `coffer sync remote set` re-sent defaults for every
option it was not given, the CLI reported only a refused connection as a lost
daemon, a synced internal-default move released the local holder before the
target write was known to land, a shelved oversized knowledge item kept its
cut-off count and raised when its material had already gone, and the
agent-registry requirement on disabled agents did not name the adoption
exception skill-manager already describes.

## What Changes

- vault-sync: `coffer sync remote set` starts from the stored remote and changes
  only the options it is given, including a custom working tree it has no flag
  for; `--with-credentials/--without-credentials` sets credential sync either
  way and leaves it as stored when neither is given; `--credential-ref ''`
  removes the push credential. A first-time remote takes today's defaults.
- mcp-gateway (behaviour within the existing scenario): every transport failure
  talking to the daemon — refused, dropped, reset or timed out — exits 3 with
  the daemon-unreachable message and no traceback.
- provider-switching (behaviour within the existing requirement): a synced move
  of the internal default releases the local holder after the target's gate,
  just before the target's write, and puts it back if that write fails.
- knowledge (behaviour within the existing requirements): shelving an oversized
  item clears its cut-off count, and shelving material that has since gone
  promotes nothing.
- agent-registry: the disabled-agent requirement names adoption as its one
  exception and says what the next reconcile and re-enabling do with it.

## Capabilities

### New Capabilities

### Modified Capabilities

- `agent-registry`
- `vault-sync`

## Impact

Backend CLI (`surfaces/cli/sync_remote_cmd.py` split out of `sync_cmd.py`,
`main.py`, `_client.py`), sync apply (`application/sync/ports.py`
`ImportNormaliser` returns a `PreWrite`, `appliers_resource.py`), the provider
internal-default normaliser, knowledge curation, `docs-site/guide/sync.md`, and
the import-linter contracts that list the CLI's sync modules.
