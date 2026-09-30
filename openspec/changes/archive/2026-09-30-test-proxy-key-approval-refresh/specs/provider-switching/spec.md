## ADDED Requirements

### Requirement: Push the proxy an approved key without a restart
The model proxy MUST hold a connection's key only once the key may go to the connection's base
URL ([credentials](../credentials/spec.md) "Hold a secret for a new destination until a person
approves it"). While a new key for a key in use waits for approval, the proxy MUST keep sending the
old key; while a new base URL waits, the proxy MUST NOT hold the key for that connection and MUST
send nothing to the new URL. When the approval is applied in the desktop app, the daemon MUST push
the proxy its state again, so the next request carries the new key or reaches the new URL, with no
restart of the daemon or the proxy.

#### Scenario: an approved key reaches the running proxy
- **GIVEN** an agent on a connection served by a running proxy, sending with the connection's key
- **WHEN** the key is replaced, then approved in the desktop app, and the connection's base URL is then moved and that change approved too
- **THEN** until each approval the proxy keeps sending the old key and sends nothing to the new URL
- **AND** after each approval the next requests carry the new key and reach the new URL, with neither process restarted
