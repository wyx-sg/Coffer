## MODIFIED Requirements

### Requirement: Wait for approval before a custom tool sends its secret
Binding a stored secret to one of an environment's headers MUST be treated as a
new destination whose target is that environment's base URL and whose slot names
the environment and the header ([secret](../secret/spec.md) "Hold a secret for
a new destination until a person approves it"): no call and no Test in that
environment carries the secret until a person approves it for that base URL, a
call before then fails with `SECRET_BINDING_PENDING` naming the approvals and
the command that approves them, and changing the environment's base URL or the
header asks again for that environment only, and so does moving the same secret
to another header ("Fix a secret's placement by its destination's definition").
Each environment is evaluated on its own: a missing secret, a pending approval or
a refusal in one environment MUST NOT stop calls in another, and only the chosen
environment's secrets are resolved for a call. A switched-off environment asks
for no approval. A group's request MUST NOT follow a redirect, and no argument
hole in a tool's path, query, headers or body MAY be filled from a stored
secret. The group MUST report each secret header's state as `present`,
`missing`, `rejected` (a person refused its binding) or `pending_approval`, per
environment and, as a whole, the worst of them in that order (`none` with no
secret header), with the ids of the approvals it waits on and of the refused
ones, and the names of the secrets concerned. A refused binding is not reported
as waiting: nothing asks the person until someone asks again.

#### Scenario: binding a stored secret to a group waits for approval
- **GIVEN** a stored secret `billing-token`
- **WHEN** a group is created with its `Authorization` header bound to `billing-token`, and an agent calls one of its tools
- **THEN** the group reports `pending_approval` naming one approval for its base URL and the secret `billing-token`, and the call fails with `SECRET_BINDING_PENDING` having sent nothing
- **AND** once the approval is applied the next call carries the secret

#### Scenario: a refused binding shows as refused, not waiting
- **GIVEN** a group whose secret binding waits for approval
- **WHEN** a person rejects the approval, and later asks again for it
- **THEN** the group reports `rejected` with the refused approval's id and the secret's name and no pending approval, and its health is `attention` for `approval_rejected`
- **AND** after asking again it reports `pending_approval` naming the new approval

#### Scenario: moving a group's base URL asks again
- **GIVEN** a group whose secret is approved for its base URL
- **WHEN** its base URL is changed
- **THEN** the group reports `pending_approval` for the new base URL and calls carry no secret until it is approved

#### Scenario: an approval in one environment does not open another
- **GIVEN** a group with environments `test` and `live`, each binding its own secret, with `test` approved and `live` pending
- **WHEN** a tool is called in `test` and in `live`, and then `test`'s base URL is changed
- **THEN** the `test` call carries its secret and the `live` call fails with `SECRET_BINDING_PENDING` naming only `live`'s approval
- **AND** after the change `test` waits for a new approval while `live`'s pending approval is unchanged

### Requirement: Manage custom tools through REST and the Custom tools page
Custom-tool groups MUST be managed through `/api/v1/custom-tools` — list
(failing groups first, each with its health, its secret's state, its calls and
failures in the last 24 hours, its environments and its tools), create (with
tools and environments), read, change, delete, add / change / remove one tool,
add / change / remove one environment, test a draft tool once without saving it,
test a saved tool, read an OpenAPI document, and preview and apply a re-import —
on the Custom tools page, which calls those routes, and with the `coffer
custom-tool` commands ("Manage custom tools from the command line"). Every test
names its environment and returns the actual target it reached (method and URL
with secret-looking query values redacted). The page MUST show each
environment's base URL, its secret state and whether it is on, and its test
panel MUST offer an environment picker. A change that waits for a secret
approval MUST report it as a pending approval on the Secrets page
([secret](../secret/spec.md) "Hold a secret for a new destination until a
person approves it"). A group's health MUST be `off` while disabled, `failing`
when its last call in 24 hours failed, `attention` while a secret of an enabled
environment is missing, waits for approval or was refused, `healthy` after a successful last
call, and `idle` with no call in 24 hours.

#### Scenario: create a custom-tool group and add a tool
- **GIVEN** the daemon is running and a stored secret `deploy-token` whose binding is approved
- **WHEN** the user creates a group `deploy` with `POST /api/v1/custom-tools` (base URL `https://deploy.example/v1`, an `Authorization` header with the scheme `Bearer` and the secret `deploy-token`), then adds a `rollback` tool with `POST /api/v1/custom-tools/deploy/tools` (method `POST`, path `/services/{service}/rollback`, a required string argument `service`)
- **THEN** reading the group lists the `rollback` tool with the changes-data flag on
- **AND** `POST /api/v1/custom-tools/deploy/test` for that tool with the argument `service=web` returns the upstream's status line

#### Scenario: a test runs a draft tool once without saving it
- **GIVEN** a group with an approved secret
- **WHEN** a draft tool that is not saved is tested with sample arguments
- **THEN** the response's status, duration and body are returned, the group's tools are unchanged, and nothing is added to the invocation log

#### Scenario: the group list puts a failing group first
- **GIVEN** one group whose last call failed, one whose last call succeeded and one disabled
- **WHEN** the groups are listed
- **THEN** the failing group comes first with health `failing`, then the healthy one, and the disabled one last with health `off`

#### Scenario: a saved tool is tested in a chosen environment and reports its target
- **GIVEN** a group with environments `test` and `live` and a saved tool `GET /status`
- **WHEN** `POST /api/v1/custom-tools/{name}/tools/status/test` is sent with `environment` = `live`
- **THEN** only `live`'s base URL receives the request, and the answer names `live` and the URL it reached

### Requirement: Show what an MCP server requires
A server's status read MUST also list what its command and settings need from this machine, worked out from the config alone and without starting the server: for a stdio server its **launcher** (the command's executable — `npx`, `uvx`, `docker`, `bunx`, `node`, `python` and the like) as a CLI that is `found`, with its version when it prints one, or `not_found`; and every **secret** its environment or headers cite — through a stored secret bound to the variable or header, or a `coffer://secret/<name>` written in a plain value — as `set`, `missing` on this machine, `waiting_approval`, or `refused` once a person refused its binding (a refusal is not a wait), naming the variable or header and the secret. A launcher's version is read once and kept until the daemon restarts; one that is not found is looked up again on every read. An HTTP server has no launcher, and no secret's value is read.

#### Scenario: a server's page lists what it requires
- **GIVEN** a stdio server started with `npx` whose environment binds one stored secret that is set, one that is missing, and one that waits for approval
- **WHEN** its status is read
- **THEN** it lists the `npx` launcher as found with its version, then each secret as `set`, `missing` and `waiting_approval` by its variable name
- **AND** a launcher that is not on this machine reads `not_found`, and an HTTP server lists its header secrets and no launcher
