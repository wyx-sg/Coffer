## MODIFIED Requirements

### Requirement: Report a channel whose secret waits for approval
A channel's adapter reads its bot token or app secret through the secret
boundary, which holds a secret that no one has approved for this channel (see
[secret](../secret/spec.md)). When that is why an adapter did not
start, the daemon MUST record the cause and report it, rather than a generic
stopped state: the channel status carries `secret_approval` with a `state` of
`pending` (waiting for the owner's approval in the Coffer app) or `refused` (the
owner declined; it stays refused until the channel's destination changes) and the
`secret_ref` it concerns, never a value. The field is absent when the adapter
runs, when the failure has any other cause, and when the channel is disabled or
not bound here. The lifecycle MUST retry on its normal failure interval, so an
approval given meanwhile starts the adapter with no restart; a pairing and the
channel's settings are untouched throughout. The Channels page and the Overview
attention item MUST name the approval (and, for `refused`, that it was refused)
instead of "not running" or a suggestion to replace the key.

#### Scenario: a channel whose secret waits for approval says so and starts once approved
- **GIVEN** an enabled channel whose secret has not been approved for it
- **WHEN** the lifecycle tries to start its adapter
- **THEN** the channel's status reports `secret_approval` with state `pending` and the secret's ref, and the adapter is not running
- **AND** once the owner approves it, the next retry starts the adapter and the field disappears, with no restart
