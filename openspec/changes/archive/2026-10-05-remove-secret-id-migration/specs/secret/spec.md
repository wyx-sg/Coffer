## MODIFIED Requirements

### Requirement: Keep secret values out of secret audit events
The events `secret_set`, `secret_revealed`, `secret_deleted`, `secret_notes_updated`,
`master_key_relocated`, `master_key_exported`, `secret_resolved`, `secret_imported` and the
`secret_approval_*` events MUST carry the ref, the name, the destination or the changed field names only. An audit payload
MUST NOT carry a secret value, and a new secret event that does MUST NOT be added.

#### Scenario: secret audit events carry the ref only
- **GIVEN** a running daemon
- **WHEN** a secret is stored and deleted through the API
- **THEN** the `secret_set` and `secret_deleted` entries each carry the ref
- **AND** none of those entries contains the secret value anywhere in its payload

### Requirement: Keep an index of what cites each secret
What cites each secret MUST be kept in an index under `derived/`
(`secret-citations.json`) — a rebuildable cache, never synced — rather than
rescanned on each read. The configs and skill files stay the source of truth.
The index MUST be rebuilt in full at daemon start and whenever the file is
missing, unreadable or of another format, and updated on every resource
register, update, rename and delete and on a skill's file changes. Listing
secrets, refusing the delete of a secret in use and releasing a secret when a
resource is deleted MUST read the index and not
rescan the resources or the skill files.

#### Scenario: a new citation shows without a rescan
- **GIVEN** a stored secret
- **WHEN** an MCP server citing it is registered, then a skill file cites its URI, then the index file is deleted and the daemon restarted
- **THEN** after each step the list shows that citer, and after the restart it gives the same answer

## REMOVED Requirements

### Requirement: Move every secret to a fixed id once
**Reason**: The move has run on every machine that held older refs; Coffer keeps no migration code once it has run.
**Migration**: None. A ref that is not `secret/<32 hex>` is no longer moved; re-add the secret from the Secrets page, which mints its id.
