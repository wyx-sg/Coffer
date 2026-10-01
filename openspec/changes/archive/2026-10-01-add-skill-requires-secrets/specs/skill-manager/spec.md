## ADDED Requirements

### Requirement: Declare the secrets a skill requires
The mapping form of a skill's `requires:` frontmatter MAY name the Coffer
secrets the skill needs under `secrets:` — `requires: {commands: [...],
secrets: [...]}` — each entry a secret name as the secret store accepts it.
The list form of `requires:` MUST stay commands only. An entry that is not a
valid secret name, and a name given twice, MUST be skipped with a warning
without failing the skill. A key of the mapping other than `commands` and
`secrets` MUST be refused: it is reported as a warning and nothing under it
is read. The declaration MUST be read from the skill's master folder each time
it is read. The skill's read model MUST carry the declared secrets as
`requires_secrets`, in the order declared, each with its `name` and whether the
secret store holds a secret under that name (`is_set`) — answered by presence
alone: no secret value is read, and no value appears in the read model or in
`coffer skill show --json`, which prints the same model. The value is set by
the person on the Secrets page, and the skill's commands receive it through
`coffer run --secret`. Declaring a secret changes nothing about delivery: the
skill is delivered whether or not the secret is set.

#### Scenario: a skill's secrets are read from the mapping form
- **GIVEN** a SKILL.md declaring `requires: {commands: [gh], secrets: [GITHUB_TOKEN, "bad name", GITHUB_TOKEN, npm.token]}`
- **WHEN** its requirements are read
- **THEN** `gh` is the one command and `GITHUB_TOKEN` and `npm.token` are the secrets, in that order
- **AND** `bad name` and the second `GITHUB_TOKEN` are skipped, each with a warning naming why

#### Scenario: an unknown key under requires is refused
- **GIVEN** a SKILL.md declaring `requires: {commands: [jq], tools: [rg], env: {A: b}}`
- **WHEN** its requirements are read
- **THEN** `jq` is the one requirement and nothing under `tools` or `env` is read
- **AND** one warning names `env` and `tools` as refused

#### Scenario: the read model says whether each declared secret is set
- **GIVEN** an imported skill declaring the secrets `GH_TOKEN` and `NPM_TOKEN`, with only `NPM_TOKEN` in the secret store
- **WHEN** the skill is read through `GET /api/v1/skills/{uid}`
- **THEN** `requires_secrets` is `GH_TOKEN` not set and `NPM_TOKEN` set, and no secret value appears in the response
- **AND** once `GH_TOKEN` is stored the skill list reports both set

### Requirement: Report a secret a skill requires that is not set
A managed skill that declares a secret the secret store does not hold MUST
raise one item in the "needs you" list (spec resource-framework "Report what
needs a person across every kind"), of kind `skill` with the skill's uid and
name, reason code `skill_missing_secret`, a reason naming each such secret as
"secret <name> is not set", and as its action the Secrets page's own write
(`POST /api/v1/secrets`) with the secret's ref and no value. Setting a secret
is the person's task, so the item MUST carry no hand-off prompt. The check
MUST be made afresh on each read, so a secret the person has just set clears
the item.

#### Scenario: a secret a skill requires that is not set raises a needs-you item
- **GIVEN** a skill `triage` declaring `GH_TOKEN`, `NPM_TOKEN` and `SLACK_TOKEN`, and a skill `publish` declaring `NPM_TOKEN`, with only `NPM_TOKEN` stored
- **WHEN** the needs-you list is read
- **THEN** there is one item, for `triage`, reason code `skill_missing_secret`, naming `GH_TOKEN` and `SLACK_TOKEN` as not set
- **AND** its action is `POST /api/v1/secrets` with the ref `secret/GH_TOKEN` and no value, and it carries no hand-off prompt
