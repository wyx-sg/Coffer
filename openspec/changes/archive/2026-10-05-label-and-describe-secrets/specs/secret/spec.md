## ADDED Requirements

### Requirement: Label and describe a secret without changing its reference
A secret's ref MUST stay its identity for life: no label or description change
moves the value or changes anything that cites it. `PUT /api/v1/secrets/notes`
(`{ref, label, description}`) MUST store, for a stored or cited ref (else 404),
a label of up to 64 characters and a description of up to 200 (longer is 422);
a field left out is unchanged and an empty value removes it. Labels and
descriptions MUST live in one versioned vault state document keyed by ref —
never beside a ciphertext — so they travel with sync. The same document records where a secret came from (`origin`: `page` for one a
person added on the Secrets page or with `coffer secret set --name`, `dialog` for one
written under a minted id by a resource dialog, an import or a service for the resource about
to cite it) and, for a dialog's, the resource that cites it (`created_for`); editing a label or
description never changes either.
`GET /api/v1/secrets` and `coffer secret list --json` MUST carry each ref's
`label`, `description` and `created_for`. Deleting a secret, and the release of
a ref when the resource citing it is deleted, MUST drop its notes. A change MUST
be audited as `secret_notes_updated` naming the ref and which fields changed,
never their text.

#### Scenario: a label and description change nothing that cites the secret
- **GIVEN** a ref an MCP server cites
- **WHEN** it is labelled "Jira PAT" and described "release bot's token"
- **THEN** the list carries the label and description, the server's config still cites the same ref, the server resolves it with no approval waiting, and the store holds the same single file

#### Scenario: notes go with the secret
- **GIVEN** a labelled, described standalone secret
- **WHEN** it is deleted
- **THEN** the notes document holds no entry for its ref

### Requirement: Mint every secret's id; a person names it
Every new secret's id MUST be minted by Coffer as `secret/<uuid4 hex>` (32
lowercase hex characters), whoever the secret is for: a standalone secret, an
MCP server's header, a channel's token, a provider's key. A resource's config
cites `secret/<hex>` in its secret slot and a file cites
`coffer://secret/<hex>`; it is the same id. A person gives a secret only a
label. `POST /api/v1/secrets` MUST accept `{label?, created_for?, value}`
without a `ref`, mint the id, store the value, keep the label and `created_for`
(the uid of the resource it is minted for) as the secret's notes, and answer
`201` with `{ref, uri}`. The Secrets page's Add secret and `coffer secret set
--name <label>` do this and show or print `coffer://secret/<id>`. A secret written under a new `secret/<hex>` ref, without the page, is a dialog's. A request
that names a `ref` MUST replace the value of a secret that exists, as before,
and MUST be refused (422) when the ref does not exist and is not itself
`secret/<32 hex>`; `proxy-token/…` refs are Coffer's own and never go through
this route. `coffer secret set <ref>` replaces an existing secret's value only.

#### Scenario: a secret added on the page gets a minted id and its label
- **GIVEN** the Secrets page
- **WHEN** a secret is added with the label "GitHub token" and a value
- **THEN** it is stored at `secret/<32 hex characters>`, the list shows it as "GitHub token", and the dialog offers `coffer://secret/<that id>` to copy

#### Scenario: a person cannot choose an id
- **GIVEN** a running daemon
- **WHEN** a client stores a value under the new ref `secret/orders-db`, and `coffer secret set --name "Orders DB"` is run
- **THEN** the first is refused with 422 and nothing is stored, and the second stores the value at `secret/<32 hex>` labelled "Orders DB" and prints its URI

### Requirement: Move every secret to a fixed id once
At daemon start every stored or cited ref that is not `secret/<32 hex>` MUST be
moved to one, except a proxy token: a standalone `secret/<name>` keeps its old
name as its label; any other ref a resource cites becomes `secret/<uuid4 hex>`
with origin `dialog` and `created_for` set to its citer's uid when exactly one resource
cites it (a standalone secret gets origin `page`).
A move writes the value at the new ref and reads it back, carries this
machine's binding, creation time, last-used stamp and the notes, repoints every
citing resource config through the resource service and the sync remote's push
token, rewrites `coffer://secret/<old>` in the skill master store's files,
deletes the old ref, and is audited as `secret_migrated` naming both refs. A
failure before any citer changed removes the new ref; one part-way leaves the
old ref in place. A second start moves nothing.

#### Scenario: start-up moves old names to fixed ids and keeps them readable
- **GIVEN** a standalone `secret/github` cited by a skill's script, a ref `postman.AUTHORIZATION` an MCP server cites, a ref `team.TOKEN` two servers cite, and a ref `mcp_server/<32 hex>/JIRA_TOKEN` a server cites
- **WHEN** the daemon starts
- **THEN** `secret/github` is now `secret/<32 hex>` labelled "github" and the script cites its new URI, each server's `postman.AUTHORIZATION` and `JIRA_TOKEN` now cites a `secret/<32 hex>`, both servers sharing `team.TOKEN` cite one new ref, each with its old value and no approval waiting
- **AND** a second start moves nothing

### Requirement: Audit every use of a secret by who used it
Every decrypt-for-use MUST be audited as `secret_resolved`: a resource's
destination (an MCP server's spawn or header, a channel adapter's start, a
provider's key, the sync push) with `{ref, destination_kind, destination_uid,
destination_name, slot}`, and a `coffer run` resolve with `{ref, name, argv0,
cwd}`; never a value or the rest of a command line. A (ref, destination, slot)
MUST be audited at most once a minute. `GET /api/v1/secrets/uses?ref=<ref>&limit=20`
MUST answer those rows newest first as `{at, actor, destination_kind,
destination_uid, destination_name, slot, argv0, cwd}`, where a `coffer run`
child is `destination_kind` `run`.

#### Scenario: a server start and a coffer run each show as a use
- **GIVEN** a standalone secret and a stored secret an MCP server resolves
- **WHEN** the server's secret is resolved for its destination and `coffer run` resolves the standalone secret
- **THEN** `GET /api/v1/secrets/uses` for each ref names the destination (the server and its slot, or `run` with the program), and no row contains a value

### Requirement: Keep an index of what cites each secret
What cites each secret MUST be kept in an index under `derived/`
(`secret-citations.json`) — a rebuildable cache, never synced — rather than
rescanned on each read. The configs and skill files stay the source of truth.
The index MUST be rebuilt in full at daemon start and whenever the file is
missing, unreadable or of another format, and updated on every resource
register, update, rename and delete and on a skill's file changes. Listing
secrets, refusing the delete of a secret in use, releasing a secret when a
resource is deleted and the move to fixed ids MUST read the index and not
rescan the resources or the skill files.

#### Scenario: a new citation shows without a rescan
- **GIVEN** a stored secret
- **WHEN** an MCP server citing it is registered, then a skill file cites its URI, then the index file is deleted and the daemon restarted
- **THEN** after each step the list shows that citer, and after the restart it gives the same answer

## MODIFIED Requirements

### Requirement: Store a secret through the API
`POST /api/v1/secrets` MUST store `{ref, value}` for a ref that exists, answer `204`, and record a
`secret_set` audit entry carrying the ref only, plus whether it replaced a value. A new secret is
stored without a `ref` (see "Mint every secret's id; a person names it"). A new secret and a replacement
are both stored at once, with no approval, because a caller that supplies a value already has it;
where a value may go is decided at each destination (see "Hold a secret for a new destination
until a person approves it"). A replacement MUST reach whatever holds the old value, such as the
model proxy, which is refreshed with the new one; the consumers that read a secret when they use
it, an MCP server's next spawn or a channel adapter's next start, get the new value then.

#### Scenario: storing a secret answers 204 and audits the ref only
- **GIVEN** a running daemon
- **WHEN** the user posts `{ref, value}` for an existing ref to `/api/v1/secrets`
- **THEN** the response is `204` and the ref reads back present
- **AND** a `secret_set` audit entry names the ref and does not contain the value

#### Scenario: replacing a value in use stores it at once
- **GIVEN** a secret an approved MCP server receives
- **WHEN** a new value is posted for its ref
- **THEN** the answer is `204`, the store holds the new value, and no approval waits
- **AND** the `secret_set` audit entry names the ref and says it replaced a value, without either value

#### Scenario: adding a standalone secret stores it at once
- **GIVEN** the protection is on
- **WHEN** a value is posted with a label and no ref
- **THEN** the answer is `201` with the minted ref, the value reads back from the store, and no approval waits

### Requirement: Read a secret on the command line without shell history
`coffer secret set --name "<label>"` (a new secret) and `coffer secret set <ref>` (an existing one) MUST take the secret from standard input, or from a hidden prompt on
a terminal, MUST reject an empty value with a non-zero exit, and MUST document `--value` as unsafe
because it lands in shell history.

#### Scenario: the command line stores a secret without it reaching shell history
- **GIVEN** a terminal,
- **WHEN** the user pipes a secret into `coffer secret set --name "<label>"`, or is prompted for it with the input hidden,
- **THEN** the secret is stored, an empty value is rejected with a non-zero exit, and passing `--value` instead prints an explicit warning that the value lands in shell history.

### Requirement: Carry references, never secrets, in resource configuration
A resource's configuration MUST carry secret references and never secret values. Each kind
declares how its refs are extracted from its own config shape; a kind that declares no extractor
cites no secrets and is never probed. A reference is resolved only at the moment of use.

#### Scenario: store and reference a secret
- **GIVEN** the user has not yet stored an HTTP secret,
- **WHEN** the user issues `POST /api/v1/secrets` (the Secrets page's Add button, or `coffer secret set`) with a `label` and the secret `value` in the request body, then registers an HTTP MCP server whose `secret_refs` cites the minted `ref` it answers,
- **THEN** the secret value is written only as Fernet ciphertext in its file under `vault/secret/` (its plaintext never reaches any file, the history database, any log, or the audit), and the server registration succeeds with the secret resolved (decrypted) at upstream-spawn time.

### Requirement: Resolve standalone secrets into one child with coffer run
A standalone secret MUST live in the store under `secret/<id>`, where `<id>` is the
minted 32 hex characters (older names are moved to one at start), and MUST be
cited from files as `coffer://secret/<id>`
([Standalone Secrets Are Named `coffer://secret/` References](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)).
`coffer run [--secret NAME|ENV=NAME]… [--env-file FILE] [--no-masking] -- cmd
args…` MUST resolve every named secret, every `coffer://secret/` value in the
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

### Requirement: Release unshared references when a resource is deleted
A resource that newly cites a `dialog` secret nothing else cites becomes its `created_for`.
Deleting a resource MUST release a secret only when it was minted for that resource
(`created_for` in the secret's notes) and nothing else cites it: no other resource and no
skill file holding its `coffer://secret/<id>`. Every other secret the resource cited is kept and
shows as not used. The first citation of a secret a resource was given (`dialog`, unclaimed or
claimed by it) needs no approval; a `page` secret needs a person the first time any resource cites it. Each release is recorded. A failed release MUST NOT turn the
already-completed deletion into an error — the secret lingers, which is the status quo, rather
than the deletion appearing to have failed.

#### Scenario: deleting a resource releases the secrets nothing else cites
- **GIVEN** a registered resource citing three secrets: two minted for it, one of which a second resource also cites, and one a person added on the page
- **WHEN** the first resource is deleted
- **THEN** the minted secret nothing else cites is removed from the store and audited, the shared one and the page-added one are kept, and a failure to release either does not fail the deletion

#### Scenario: a dialog's secret is the server's and a page's is not
- **GIVEN** a secret stored under a minted ref and labelled before any resource cites it, and another added on the page
- **WHEN** a new MCP server cites the first, and another new server cites the second
- **THEN** the first needs no approval and is released when its server is deleted, while the second waits for a person and is kept

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
listing reads what cites each secret from the citation index (see "Keep an index of what cites each secret"), decrypts nothing and records no audit entry; who used a secret is read from `GET /api/v1/secrets/uses` (see "Audit every use of a secret by who used it"). It MUST leave out an
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

### Requirement: Keep secret values out of secret audit events
The events `secret_set`, `secret_revealed`, `secret_deleted`, `secret_notes_updated`, `secret_migrated`,
`master_key_relocated`, `master_key_exported`, `secret_resolved`, `secret_imported` and the
`secret_approval_*` events MUST carry the ref, the name, the destination or the changed field names only. An audit payload
MUST NOT carry a secret value, and a new secret event that does MUST NOT be added.

#### Scenario: secret audit events carry the ref only
- **GIVEN** a running daemon
- **WHEN** a secret is stored and deleted through the API
- **THEN** the `secret_set` and `secret_deleted` entries each carry the ref
- **AND** none of those entries contains the secret value anywhere in its payload

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
it would become: the label a skill's secret will get, the server's own
`secret_refs` slot for a server. The scan also reports how many files and
servers it read (`files_checked`, `servers_checked`).

`POST /api/v1/secrets/import` (the chosen finding ids, and an optional dry run
that writes nothing) MUST move each chosen value:

- a skill's value is stored at a minted `secret/<uuid4 hex>` labelled with the
  proposed name and, once the store reads the same value back, replaced in its
  file by `coffer://secret/<id>`, atomically and keeping the file's mode; a file that cannot be rewritten
  leaves its findings skipped as `stored`, naming the secret, and importing the
  same findings again retries the file;
- a server's value is stored under a new ref of the server's own
  (`secret/<uuid4 hex>`, minted for that server), and the server's config is changed through the
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
- **THEN** the dry run changed nothing, and the import stores the value under a minted id, which reads back the same
- **AND** the file cites `coffer://secret/<id>` in place of the value with its mode unchanged, and one `secret_imported` entry names the secret without the value

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
