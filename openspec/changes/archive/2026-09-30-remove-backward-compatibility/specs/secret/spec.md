## MODIFIED Requirements

### Requirement: Hold a secret for a new destination until a person approves it
A destination is a place Coffer sends a secret's plaintext: an MCP server's
environment variable or HTTP header, a channel adapter's secret, the sync
remote's push token, and — through the same service call — a provider
connection's key and a custom tool's authentication. Every consumer MUST name
the destination and the **target** that receives the value (a stdio server's
whole command line with its working directory and non-secret environment, an
HTTP URL, a git URL, a channel's platform and app) before it resolves a secret,
and MUST inject nothing into a target no person approved: the attempt answers
`SECRET_BINDING_PENDING` (409) naming the pending approvals. Citing an existing
secret from a destination that did not cite it, and changing the target of one
that did, each record a pending approval, once per target; a later target
supersedes the approval for the earlier one. A binding already approved for
its target MUST keep working. A binding is approved without a person only when
its value was supplied for it — the ref was never bound anywhere, is not a
standalone `secret/` name, and was stored within the last five minutes — or
while the protection is switched off. Approving MUST
take a presence grant (`POST /api/v1/secrets/approvals/{id}/approve`);
refusing (`POST .../reject`) MUST NOT. `GET /api/v1/secrets/approvals`
lists approvals, having first evaluated every current destination, and marks
superseded those nothing asks for any more.

#### Scenario: citing an existing secret from a new MCP server waits for approval
- **GIVEN** a secret an MCP server is already approved to receive
- **WHEN** a second MCP server citing the same ref is registered, and a session reaches its tools
- **THEN** the second server is not spawned with the secret, the attempt answers `SECRET_BINDING_PENDING`, and one pending approval names the ref, the new server and its command line
- **AND** the first server keeps receiving the secret

#### Scenario: changing where a secret goes asks again
- **GIVEN** an MCP server whose secret is approved for its command line
- **WHEN** its command is changed to another program
- **THEN** the secret is withheld and a pending approval names the new command line
- **AND** after the approval is applied with a presence grant the server receives the secret again

#### Scenario: moving a provider connection's base URL asks again
- **GIVEN** a provider connection whose key the model proxy already receives
- **WHEN** its base URL is changed, and separately its key is replaced
- **THEN** the key is not handed to the proxy or the engine for the new URL until the approval naming that URL is applied, and the replaced key waits sealed until its own approval is applied
- **AND** once each is approved the proxy is refreshed with the key

#### Scenario: a value supplied for its destination needs no approval
- **GIVEN** a secret stored a moment ago under a ref nothing has ever received
- **WHEN** a destination citing that ref first uses it
- **THEN** the secret is injected and the binding is recorded as approved

#### Scenario: bindings in use at upgrade keep working
- **GIVEN** a vault whose resources and sync remote cite secrets before the boundary existed
- **WHEN** the daemon that has the boundary starts for the first time
- **THEN** every binding in use is approved for its current target, and starting again adopts nothing further

### Requirement: Keep the master key behind a storage port chosen by the build
Where the master key lives MUST be decided by how the build was made, never by
a setting or an environment variable. A signed release stamped with Coffer's
Keychain access group MUST keep the key only in one data-protection Keychain
item in that group (service `coffer`, account `master-key`) with no
user-presence flag, so the daemon reads it unattended; it MUST NOT read a key
from the key file or the login-keychain item, and MUST refuse to relocate the
key to a file. A build without the stamp is a development build: it keeps the
arrangement of "Keep the master key in exactly one place", and reports itself
as development (see "Release plaintext only to a present human in the desktop
app").

#### Scenario: a signed build keeps its key in its access group only
- **GIVEN** a signed build with an empty secret store
- **WHEN** the key is resolved
- **THEN** the key is created in the access-group item, no key file is written, and the manager reports the access group as the key's location
- **AND** a later request to relocate the key to the file is refused

#### Scenario: the access-group item carries no presence flag
- **GIVEN** the access-group backend
- **WHEN** it writes and reads the master key
- **THEN** every query names the data-protection keychain and Coffer's access group, and none carries an access-control (presence) flag

#### Scenario: a signed build moves a file key into its access group
- **GIVEN** a signed build's Keychain item that is empty and a master key in the key file
- **WHEN** the key is resolved
- **THEN** the item holds the key, the file is gone, and the manager reports the access group as the key's location
- **AND** a later request to relocate the key to the file is refused

## REMOVED Requirements

### Requirement: Migrate legacy keychain secrets once at startup
**Reason**: 1.0 keeps no backward compatibility; the pre-0.2 OS-keychain install base is retired, so the startup move of legacy keychain secrets into the encrypted store is deleted with its module.
**Migration**: One-time manual upgrade step before installing 1.0: on a vault that was ever run by a pre-0.2 build, confirm every cited ref is in the encrypted store (the Secrets page shows none as "Missing on this Mac"); any that is missing is re-entered by hand. Leftover `coffer` entries in the login keychain other than `master-key` may then be deleted with Keychain Access.
