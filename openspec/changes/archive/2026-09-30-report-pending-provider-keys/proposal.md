## Why

`coffer provider edit --secret` for a key in use, `--base-url` for a connection whose key already goes somewhere, and `coffer provider add --credential-ref` with a key another connection uses all save a change that waits for approval in the Coffer app. The provider commands still printed success and exited `0`. Every other command that saves such a change uses the shared helper in `surfaces/cli/_approvals.py`, which prints what waits and exits `9`.

## What Changes

- `coffer provider add` and `coffer provider edit` report what waits through the shared helper. They print `waiting for approval in the Coffer app` with each approval's id and exit `9`, or wait for the answer with the new `--wait` option.
- The helper finds what a destination waits on by its uid (a pending binding) and by the refs it cites (a pending replacement of a value in use), because a replacement is held against the secret and not against a destination.
- `coffer provider edit` reports only after a change to the base URL or the key; a rename or description change never waits.

## Capabilities

### New Capabilities

### Modified Capabilities
- `credentials`: the provider commands join the list of commands that answer a pending approval by waiting or exiting `9`.

## Impact

- Backend: `surfaces/cli/_approvals.py`, `surfaces/cli/provider_cmd.py`.
- Tests: `tests/integration/security/test_secret_boundary.py`.
- Docs: the providers guide and the generated CLI reference.
