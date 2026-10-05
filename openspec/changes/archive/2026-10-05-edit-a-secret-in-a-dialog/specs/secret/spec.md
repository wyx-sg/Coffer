## MODIFIED Requirements

### Requirement: Mint every secret's id; a person names it
Every new secret's id MUST be minted by Coffer as `secret/<uuid4 hex>` (32
lowercase hex characters), whoever the secret is for: a standalone secret, an
MCP server's header, a channel's token, a provider's key. A resource's config
cites `secret/<hex>` in its secret slot and a file cites
`coffer://secret/<hex>`; it is the same id. A person gives a secret only a
label and, optionally, a description. `POST /api/v1/secrets` MUST accept
`{label?, description?, created_for?, value}` without a `ref`, mint the id,
store the value, keep the label, the description (up to 200 characters) and
`created_for` (the uid of the resource it is minted for) as the secret's notes,
and answer `201` with `{ref, uri}`. The Secrets page's Add secret and `coffer
secret set --name <label> [--description <text>]` do this and show or print `coffer://secret/<id>`. A secret written under a new `secret/<hex>` ref, without the page, is a dialog's. A request
that names a `ref` MUST replace the value of a secret that exists, as before,
and MUST be refused (422) when the ref does not exist and is not itself
`secret/<32 hex>`; `proxy-token/…` refs are Coffer's own and never go through
this route. `coffer secret set <ref>` replaces an existing secret's value only.

#### Scenario: a secret added on the page gets a minted id and its label
- **GIVEN** the Secrets page
- **WHEN** a secret is added with the label "GitHub token", the description "release bot's token" and a value
- **THEN** it is stored at `secret/<32 hex characters>`, the list shows it as "GitHub token" with that description, and the dialog offers `coffer://secret/<that id>` to copy

#### Scenario: a person cannot choose an id
- **GIVEN** a running daemon
- **WHEN** a client stores a value under the new ref `secret/orders-db`, and `coffer secret set --name "Orders DB"` is run
- **THEN** the first is refused with 422 and nothing is stored, and the second stores the value at `secret/<32 hex>` labelled "Orders DB" and prints its URI

### Requirement: Resolve standalone secrets into one child with coffer run
A standalone secret MUST live in the store under `secret/<id>`, where `<id>` is the
minted 32 hex characters (older names are moved to one at start), and MUST be
cited from files as `coffer://secret/<id>`
([Standalone Secrets Are Named `coffer://secret/` References](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)).
`coffer run [--secret NAME|ENV=NAME|ENV=coffer://secret/<id>]… [--env-file FILE] [--no-masking] -- cmd
args…` MUST accept a secret as its name or as its `coffer://secret/<id>` URI
(a bare URI sets the variable the name would; skills cite a secret in the URI
form, which the citation index sees, so the secret lists the skill under Used
by), and MUST resolve every named secret, every `coffer://secret/` value in the
env file and every such value in its own environment through
`POST /api/v1/secrets/resolve`, which MUST answer standalone names
only and MUST record one `secret_resolved` entry per name carrying the ref, the name,
the program and the working directory and never the value or the rest of the
arguments. It MUST answer only a secret a person granted to local programs: the
`local_process` destination (uid `coffer-run`, slot `env`), approved in the
desktop app with a presence grant like any other destination, and never approved
by the build's default, by the approval switch being off, or by a value having
just been supplied — whoever runs `coffer run`, an agent included, owns the
child and can read what it is handed. A resolve naming any secret without the
grant MUST read no value, MUST start nothing, and MUST answer
`SECRET_BINDING_PENDING` with the request waiting in the desktop app
(`SECRET_BINDING_REJECTED` once a person refused it). `POST
/api/v1/secrets/local-access/request {name}` MUST record that request without
granting it — after a person refused one, asking this way retires the refusal
and puts a new request up, while `coffer run` alone stays refused; asked from
the desktop app, the request is approved on the spot under the presence check,
as any save there is — and `POST /api/v1/secrets/local-access/revoke {name}` MUST withdraw
the grant and any request at once, without a presence grant, and record
`secret_local_access_revoked`. A request MUST keep waiting when approvals are
brought up to the configuration, since no configuration asks for it. The values MUST be set only in the child's environment; the child's
standard output and error MUST have every exact value of eight characters or
more replaced by `***`, including a value split across two reads, unless
`--no-masking` is given; the child's exit status MUST pass through. The docs
MUST say that masking guards against accidents and does not hide a granted
secret from an agent that runs the command, and that a secret an agent should
only use stays without the grant and reaches its service through Coffer.

#### Scenario: coffer run sets a secret only in the child
- **GIVEN** a standalone secret `db-password`
- **WHEN** `coffer run --secret db-password -- <cmd>` runs a command that reports whether `DB_PASSWORD` is set
- **THEN** the child sees the value in `DB_PASSWORD` while the calling process's environment does not change
- **AND** one `secret_resolved` entry names `db-password` and the program and does not contain the value

#### Scenario: coffer run masks the value in the child's output
- **GIVEN** a standalone secret whose value the child prints, split across two writes
- **WHEN** it runs under `coffer run`
- **THEN** the output shows `***` where the value was and never the value

#### Scenario: coffer run gets nothing until a person grants the secret
- **GIVEN** a standalone secret never granted to local programs, on a build whose approval switch is on or off
- **WHEN** a resolve names it
- **THEN** it is refused with `SECRET_BINDING_PENDING`, no value is returned and no `secret_resolved` entry is recorded
- **AND** a pending approval for the `local_process` destination waits in the desktop app, saying an agent's program could read the value

#### Scenario: asking for the grant again after a refusal puts a new request up
- **GIVEN** a standalone secret whose local-process request a person refused
- **WHEN** the grant is asked for again (Allow coffer run… on the Secrets page)
- **THEN** a new request waits in the desktop app and no refusal is answered
- **AND** a resolve still gets no value until the person approves it

#### Scenario: allowing coffer run in the desktop app asks for Touch ID at once
- **GIVEN** a standalone secret without the grant, open on the Secrets page in the desktop app
- **WHEN** the person presses Allow coffer run…
- **THEN** the presence prompt opens at once and approves exactly that request, with no approvals sheet to open

#### Scenario: coffer run without a grant starts nothing and prints no value
- **GIVEN** a standalone secret without the grant, named by `--secret` or by a `coffer://secret/` value in the environment
- **WHEN** `coffer run` is asked to start a command with it
- **THEN** the command does not start, the exit status is not zero, and the output points to the Coffer app and holds no value

#### Scenario: a granted secret reaches coffer run until the grant is withdrawn
- **GIVEN** a standalone secret whose local-process request a person approved with a presence grant
- **WHEN** a resolve names it, the grant is revoked, and a resolve names it again
- **THEN** the first resolve returns the value and the second is refused
- **AND** the listing marks it readable by local processes only while the grant stands, and the revoke is audited

#### Scenario: a resource's secret cannot be resolved by coffer run
- **GIVEN** an MCP server's token stored under its minted ref
- **WHEN** a resolve names that ref or any name that is not a stored standalone secret
- **THEN** it is refused and no value is returned
