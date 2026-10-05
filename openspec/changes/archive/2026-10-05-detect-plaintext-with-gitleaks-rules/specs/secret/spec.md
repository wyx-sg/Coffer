## ADDED Requirements

### Requirement: Detect plaintext secrets with the bundled rules
Coffer MUST decide what is a plaintext secret with one detector, used by
**Find plaintext keys** (see "Move plaintext secrets in managed resources into
the store") and by vault sync's check before a push
([vault-sync](../vault-sync/spec.md) "Refuse to push a plaintext secret").

The detector MUST run the rules of a pinned gitleaks release, shipped with
Coffer as a rule file that names its source, release, commit and licence, with
gitleaks' MIT licence beside it. Each rule is applied as gitleaks applies it:
its pattern, its secret group, its entropy threshold, its keywords, its path
condition, and its own and the global allowlists. A gitleaks binary MUST NOT
be required.

On top of those rules Coffer MUST NOT report a secret reference
(`coffer://secret/<id>`, or the `secret/<id>` a resource's `secret_refs`
holds), an interpolation (`$VAR`, `${VAR}`, `{{…}}`), a placeholder (`<…>`,
`xxx`, `your-…`, `changeme`, `example…`), code that names a value rather than
holding one, or a line holding `coffer run`; and it MUST also report a value of
at least eight characters assigned to a password-named key, whatever its
entropy, and a password inside a URL (`scheme://user:<value>@host`).

Each finding MUST name the rule that found it — the gitleaks rule id
(`stripe-access-token`, `generic-api-key`) or Coffer's own (`coffer-…`) — and
where the value is: the line, and its place on that line. A value two rules
find is one finding. No finding carries the value.

#### Scenario: a vendor token is found and named by its rule
- **GIVEN** a skill script holding a Stripe secret key and an Anthropic API key, neither assigned to a secret-sounding name
- **WHEN** the scan runs
- **THEN** each is a finding naming its file, its line and its rule, `stripe-access-token` and `anthropic-api-key`
- **AND** the response contains neither value

#### Scenario: a secret reference is not a finding though it looks like a key
- **GIVEN** a skill whose `.env` holds `API_KEY=coffer://secret/<id>`, and an MCP server whose document cites `secret/<id>` in its `secret_refs`
- **WHEN** the scan runs, and a sync round reads both files
- **THEN** neither reports anything

#### Scenario: a weak password and a password in a URL are found
- **GIVEN** a skill script with `DB_PASSWORD=` followed by a short, low-entropy password, and `DATABASE_URL=` a `postgres://` URL carrying a password
- **WHEN** the scan runs
- **THEN** both are findings, named `coffer-password-assignment` and `coffer-url-password`

#### Scenario: the bundled rules say where they came from
- **GIVEN** the rule file Coffer ships
- **WHEN** it is read
- **THEN** it names gitleaks, the release, the commit and the MIT licence, and the licence file is beside it
- **AND** every rule of that release is either in the file or listed in its header as one that could not be translated

## MODIFIED Requirements

### Requirement: Move plaintext secrets in managed resources into the store
`POST /api/v1/secrets/scan` MUST report every plaintext secret in what Coffer
manages, and MUST NOT return a value:

- **skills** — every text file of a skill in the master store (Coffer's own
  bundled skills excepted), read with the bundled rules (see "Detect plaintext
  secrets with the bundled rules");
- **MCP servers** — a registered server's stdio `env` value, HTTP `headers`
  value, or HTTP API (custom tool) `headers` value that the bundled rules find
  when read with its key, or whose name says password, secret, token, key or
  authorization, or that is a `Bearer`/`Token` credential.

A value that is already a reference (`coffer://secret/…`), an interpolation
(`$VAR`, `${VAR}`, `{{…}}`), a placeholder (`<…>`, `xxx`, `your-…`,
`changeme`, `example…`) or code is not a finding. Each finding carries a stable
id, its source (`skill` or `mcp_server`), the resource's name, where it is
(a skill's file and line; a server's `env` or `header` and its key), the rule
that found it, and what it would become: the label a skill's secret will get,
the server's own `secret_refs` slot for a server. The scan also reports how
many files and servers it read (`files_checked`, `servers_checked`).

`POST /api/v1/secrets/import` (the chosen finding ids, and an optional dry run
that writes nothing) MUST move each chosen value:

- a skill's value is stored at a minted `secret/<uuid4 hex>` labelled with the
  proposed name and, once the store reads the same value back, replaced in its
  file by `coffer://secret/<id>`, atomically and keeping the file's mode; a value
  that spans lines, such as a private key, is replaced whole; a file that cannot be rewritten
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
resource, place, the rule that found it and what it becomes, all ticked; Review changes runs the dry
run and lists the secrets it would add and the files and servers it would
change; Apply moves them and reports what moved and what was skipped and why. A
scan that finds nothing says how many files and servers it read.

#### Scenario: a scan names plaintext secrets in skills and MCP servers without their values
- **GIVEN** a skill whose script assigns a token, a stdio MCP server whose `env` holds a password, and an HTTP API server whose `Authorization` header holds a bearer token
- **WHEN** the scan runs
- **THEN** all three are reported with their resource, place, rule and what each becomes, and the response contains none of the values

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

#### Scenario: a private key in a skill moves into the store whole
- **GIVEN** a skill file holding a PEM private key over several lines
- **WHEN** the scan runs and the finding is imported
- **THEN** the finding names the key's first line and the rule `private-key`
- **AND** the file cites one `coffer://secret/<id>` where the whole block was, and the store holds the whole block
