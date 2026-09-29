## ADDED Requirements

### Requirement: Spawn a server with a secret only once its binding is approved
Before it spawns a stdio server or connects to an HTTP server with credential
refs, the gateway MUST ask the secret boundary whether each ref may go to that
server's target — the stdio command line with its working directory and
non-secret environment, or the HTTP URL — and MUST NOT start the server with
any secret a person has not approved for that target
([credentials](../credentials/spec.md) "Hold a secret for a new destination
until a person approves it"). The refused attempt surfaces as
`SECRET_BINDING_PENDING` with "waiting for approval in the Coffer app", and the
server is reachable as soon as the approval is applied, with no restart.

#### Scenario: a server whose secret is not approved is not spawned with it
- **GIVEN** a registered stdio server citing a secret that is approved for a different command line
- **WHEN** the gateway is asked to spawn it
- **THEN** nothing is spawned, the failure is `SECRET_BINDING_PENDING` naming the pending approval
- **AND** once the approval is applied the next spawn receives the secret in its environment

### Requirement: Mark a stdio server whose environment carries a secret
The resource representation of every MCP server MUST carry
`secrets_readable_by_local_processes`, true for a stdio server whose
environment carries at least one credential ref: the secret sits in the
server's initial environment, which any process of the same user can read, so
the UI labels such a server "readable by other processes on this Mac" and
nothing describes Coffer as protecting it. An HTTP server, whose headers the
gateway injects itself, and a stdio server with no secret, carry false.

#### Scenario: a stdio server with a secret is marked readable by local processes
- **GIVEN** a stdio server citing a credential ref, a stdio server citing none, and an HTTP server citing one
- **WHEN** the resources are read through the API
- **THEN** only the first carries `secrets_readable_by_local_processes: true`
