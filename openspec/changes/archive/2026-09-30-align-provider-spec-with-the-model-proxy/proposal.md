## Why

Two passages of the provider-switching spec still describe the build before the
local model proxy. The scenario "route an openai-compatible connection to
Claude Code with its scope" expects an `apiKeyHelper` running `provider key
--connection-uid <uid>` and a `GET /providers/{uid}/key` route; neither exists,
and the same spec's "Project into Claude Code settings without clobbering them"
already says the helper prints the agent's proxy token. "Fail over only before
the first content byte" bounds the held response to "a few kilobytes and
seconds", while the proxy holds up to 64 KiB for up to 5 seconds.

## What Changes

- The scenario's outcome names the `proxy token --agent-uid` helper and the
  proxy routing that agent's requests to the scoped connection with its key.
- The failover requirement states the hold bound the proxy applies: 64 KiB and
  5 seconds.
- The spec's Purpose no longer lists proxying and failover as out of scope, and
  no longer calls the boot self-check the only reconciliation; protocol
  translation stays out of scope.

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: the scoped-routing scenario and the failover hold bound
  match the model proxy.

## Impact

- Spec text only; no code, route or contract changes.
