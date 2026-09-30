## Why

When a secret approval is applied, the daemon asks the model proxy's supervisor to push the proxy its state again, so a replaced key or a moved base URL takes effect without a restart. No test asserted it, and no requirement stated it.

## What Changes

- A new provider-switching requirement: the proxy holds a key only once it may go to the connection's base URL, keeps the old key while a new one waits, and receives the approved key on the next push after the approval, with neither process restarted.
- An integration test drives a real in-process daemon attached to a real proxy app and a recording upstream through a key rotation and a base URL move, each approved in turn.

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: states when the proxy receives an approved key.

## Impact

- Tests: `tests/integration/model_proxy/test_key_approval_refresh.py`.
- Docs: the model proxy architecture page.
