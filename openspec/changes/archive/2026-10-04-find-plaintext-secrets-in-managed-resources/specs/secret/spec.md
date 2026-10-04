## ADDED Requirements

### Requirement: Move plaintext secrets in managed resources into the store
`POST /api/v1/secrets/scan` MUST report every plaintext secret in what Coffer
manages, and MUST NOT return a value:

- **skills** — every text file of a skill in the master store (Coffer's own
  bundled skills excepted): an assignment whose name says password, secret,
  token or key, or a well-known token shape;
- **MCP servers** — a registered server's stdio `env` value, HTTP `headers`
  value, or HTTP API (custom tool) `headers` value whose name says password,
  secret, token, key or authorization, or whose value is a well-known token
  shape or a `Bearer`/`Token` credential.

A value that is already a reference (`coffer://secret/…`), an interpolation
(`$VAR`, `${VAR}`, `{{…}}`), a placeholder (`<…>`, `xxx`, `your-…`,
`changeme`, `example…`) or code is not a finding. Each finding carries a stable
id, its source (`skill` or `mcp_server`), the resource's name, where it is
(a skill's file and line; a server's `env` or `header` and its key), and what
it would become: a standalone secret name for a skill, the server's own
`secret_refs` slot for a server. The scan also reports how many files and
servers it read (`files_checked`, `servers_checked`).

`POST /api/v1/secrets/import` (the chosen finding ids, and an optional dry run
that writes nothing) MUST move each chosen value:

- a skill's value is stored as `secret/<proposed name>` and, once the store
  reads the same value back, replaced in its file by `coffer://secret/<name>`,
  atomically and keeping the file's mode; a name already holding a different
  value is skipped with its file untouched; a file that cannot be rewritten
  leaves its findings skipped as `stored`, naming the secret, and importing the
  same findings again retries the file;
- a server's value is stored under a new ref of the server's own
  (`mcp_server/<random>/<key>`), and the server's config is changed through the
  resource service to drop the plaintext entry and cite the ref in
  `secret_refs` under the same key — so the change is validated, audited and
  reconciled like any edit, and, its value supplied for it moments ago, needs
  no approval (see "Hold a secret for a new destination until a person approves it").
  A server whose config cannot be changed leaves its findings skipped with the
  reason and nothing stored.

Each value stored MUST be audited as `secret_imported`, naming the secret or
ref and where it came from, never the value.

The Find plaintext keys dialog lists the findings grouped by source, each by
resource, place and what it becomes, all ticked; Review changes runs the dry
run and lists the secrets it would add and the files and servers it would
change; Apply moves them and reports what moved and what was skipped and why. A
scan that finds nothing says how many files and servers it read.

#### Scenario: a scan names plaintext secrets in skills and MCP servers without their values
- **GIVEN** a skill whose script assigns a token, a stdio MCP server whose `env` holds a password, and an HTTP API server whose `Authorization` header holds a bearer token
- **WHEN** the scan runs
- **THEN** all three are reported with their resource, place and what each becomes, and the response contains none of the values

#### Scenario: references, interpolations and placeholders are not findings
- **GIVEN** a server whose `env` holds `${API_TOKEN}`, `<your-token>` and a non-secret `LOG_LEVEL=debug`, and a skill citing `coffer://secret/github`
- **WHEN** the scan runs
- **THEN** none of them is reported

#### Scenario: importing a skill's value leaves a reference in its file
- **GIVEN** a skill finding
- **WHEN** it is imported, first as a dry run
- **THEN** the dry run changed nothing, and the import stores the value under its standalone name, which reads back the same
- **AND** the file cites `coffer://secret/<name>` in place of the value with its mode unchanged, and one `secret_imported` entry names the secret without the value

#### Scenario: importing a server's value moves it into the server's secret refs
- **GIVEN** a stdio MCP server finding and an HTTP header finding
- **WHEN** they are imported
- **THEN** each server's config no longer holds the value, cites a new ref of its own in `secret_refs` under the same key, and that ref holds the value
- **AND** the server resolves the secret with no approval waiting, and a later scan reports neither

#### Scenario: a file that cannot be rewritten keeps its key and says so
- **GIVEN** a skill finding in a file Coffer cannot write
- **WHEN** it is imported
- **THEN** nothing is reported moved, the finding is skipped as `stored` naming its secret, the file is unchanged and the store holds the value
- **AND** importing the same finding again once the file is writable moves it and rewrites the file

#### Scenario: a scan that finds nothing says how much it read
- **GIVEN** a skill and a server holding no plaintext secret
- **WHEN** the scan runs
- **THEN** it reports no findings, at least one file read and one server read

## MODIFIED Requirements

### Requirement: Keep secret values out of secret audit events
The events `secret_set`, `secret_revealed`, `secret_deleted`,
`master_key_relocated`, `master_key_exported`, `secret_resolved`, `secret_imported` and the
`secret_approval_*` events MUST carry the ref, the name or the destination only. An audit payload
MUST NOT carry a secret value, and a new secret event that does MUST NOT be added.

#### Scenario: secret audit events carry the ref only
- **GIVEN** a running daemon
- **WHEN** a secret is stored and deleted through the API
- **THEN** the `secret_set` and `secret_deleted` entries each carry the ref
- **AND** none of those entries contains the secret value anywhere in its payload
