## MODIFIED Requirements

### Requirement: Carry a channel's document but not its adapter
A `channel` document MUST travel while its adapter does not. A channel is an
inbound surface — a polled bot or a held websocket connection, each of which a
platform serves to one consumer at a time — so the document names the one machine that may answer: `runs_on`, the
`machine_id` whose daemon starts the adapter ([channels](../channels/spec.md) "Bind each channel to the one machine that runs it"). The other
machine therefore holds the channel's configuration, its credential references
and its pairings, so taking over a bot is a rebind rather than a
re-registration.

A channel's machine binding is not the retired machine axis of `scope` coming
back. Reach is "which agents, here" — a local answer each machine gives itself.
The binding is "which machine runs the adapter" — one answer the machines
share, so it lives in the channel's config and travels with it. A binding
records a fact no machine can state alone, because it is about which of them
acts.

#### Scenario: a channel document names the machine that runs it
- **GIVEN** a `channel` configured on one machine and bound to it
- **WHEN** a round exports the vault
- **THEN** the working tree holds a document for the channel like any other resource
- **AND** that document names the bound machine's `machine_id` as the one that runs its adapter

### Requirement: Carry credentials as ciphertext only
Credentials MUST travel as Fernet **ciphertext only**, and only when the remote
is configured to carry it.

#### Scenario: a synced channel carries a credential reference, never a secret
- **GIVEN** a `channel` whose configuration cites a credential ref for its bot
  token or its app secret,
- **WHEN** a round exports the vault,
- **THEN** the channel's document in the working tree holds the ref and no
  secret material, and the secrets themselves appear only as Fernet ciphertext
  and only when the remote is configured to carry credentials.
