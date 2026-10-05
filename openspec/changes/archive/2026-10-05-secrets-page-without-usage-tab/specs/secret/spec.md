## MODIFIED Requirements

### Requirement: Audit every use of a secret by who used it
Every decrypt-for-use MUST be audited as `secret_resolved`: a resource's
destination (an MCP server's spawn or header, a channel adapter's start, a
provider's key, the sync push) with `{ref, destination_kind, destination_uid,
destination_name, slot}`, and a `coffer run` resolve with `{ref, name, argv0,
cwd}`; never a value or the rest of a command line. A (ref, destination, slot)
MUST be audited at most once a minute. The rows are read in Activity; no secrets
route lists them.

#### Scenario: a server start and a coffer run each show as a use
- **GIVEN** a standalone secret and a stored secret an MCP server resolves
- **WHEN** the server's secret is resolved for its destination and `coffer run` resolves the standalone secret
- **THEN** one `secret_resolved` entry per ref names the destination (the server and its slot, or the program and folder of the `coffer run`), and no entry contains a value

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
arguments. The values MUST be set only in the child's environment; the child's
standard output and error MUST have every exact value of eight characters or
more replaced by `***`, including a value split across two reads, unless
`--no-masking` is given; the child's exit status MUST pass through. The docs
MUST say that this guards against accidents and does not hide a secret from an
agent that runs the command.

#### Scenario: coffer run sets a secret only in the child
- **GIVEN** a standalone secret `db-password`
- **WHEN** `coffer run --secret db-password -- <cmd>` runs a command that reports whether `DB_PASSWORD` is set
- **THEN** the child sees the value in `DB_PASSWORD` while the calling process's environment does not change
- **AND** one `secret_resolved` entry names `db-password` and the program and does not contain the value

#### Scenario: coffer run masks the value in the child's output
- **GIVEN** a standalone secret whose value the child prints, split across two writes
- **WHEN** it runs under `coffer run`
- **THEN** the output shows `***` where the value was and never the value

#### Scenario: a resource's secret cannot be resolved by coffer run
- **GIVEN** an MCP server's token stored under its minted ref
- **WHEN** a resolve names that ref or any name that is not a stored standalone secret
- **THEN** it is refused and no value is returned

### Requirement: List every stored and cited secret with what uses it
`coffer secret list` and `GET /api/v1/secrets` MUST list every ref the
store holds and every ref a registered resource cites, each with whether the
store holds it, whether this Mac's key can open it (`locked`), when it was
stored (`created_at`) and when a consumer last had it decrypted on this Mac
(`last_used_at`, stamped at most once a minute and not by a reveal), the resources that cite it with the slot each cites it under, its label, description and
`created_for`, its `coffer://secret/<id>` and the skills whose files cite that URI, whether
nothing references it (`unreferenced`), the destinations it is approved for or
waits on, and whether another process of this user can read the value where
Coffer puts it (a standalone secret, or a stdio MCP server's environment). The
listing reads what cites each secret from the citation index (see "Keep an index of what cites each secret"), decrypts nothing and records no audit entry; who used a secret is audited, not listed here (see "Audit every use of a secret by who used it"). It MUST leave out an
agent's model-proxy token (`proxy-token/<agent name>`): Coffer mints it and the
agent fetches it itself, so no person enters, replaces or cites it. A delete MUST also be
refused with `SECRET_IN_USE` while a skill in the master store cites a
standalone secret's URI, naming that skill, and a delete that removes a ref
MUST forget its approved destinations.

#### Scenario: the command line lists every cited ref with its presence
- **GIVEN** a registered MCP server citing a stored ref and a registered model provider citing a ref the store does not hold
- **WHEN** the user runs `coffer secret list`
- **THEN** both refs are listed
- **AND** the MCP server's ref is shown as present and the provider's ref as missing

#### Scenario: a secret nothing references is listed as unreferenced
- **GIVEN** a standalone secret no resource and no skill cites, and another that a skill cites by URI
- **WHEN** the secrets are listed
- **THEN** the first is marked unreferenced and readable by local processes
- **AND** the second names the skill, and deleting it is refused naming that skill

#### Scenario: the list says when each secret was created and last used
- **GIVEN** a standalone secret stored and never used
- **WHEN** the secrets are listed, then `coffer run` resolves it, then they are listed again
- **THEN** the first listing carries its `created_at` and no `last_used_at`
- **AND** the second carries a `last_used_at` no later than now

#### Scenario: an agent's model-proxy token is not listed
- **GIVEN** a stored agent model-proxy token and a stored standalone secret
- **WHEN** the secrets are listed
- **THEN** only the standalone secret is listed
