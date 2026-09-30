## MODIFIED Requirements

### Requirement: Move plaintext secret files into the store
`POST /api/v1/credentials/scan` (`coffer credentials scan`) MUST report every
plaintext secret in `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json`
(a flat map of strings) and in the skill master store (assignments whose name
says password, secret, token or key, and well-known token shapes) by file,
line, key and proposed name, and every skill that still mentions
`~/.coffer/secrets/`; it MUST NOT return a value. When a skill still mentions
`~/.coffer/secrets/`, the scan MUST also carry `handoff`, a prompt (Principle
IV, AI-Native) that asks the person's agent to rewrite each such command to get
its value through `coffer run --secret ENV=NAME -- …` or `coffer run --env-file`
with `coffer://secret/<name>` references, to show the person the diff, and
never to print, copy or read a value; the prompt names only each mention's
skill, file, line and the path it reads, and the secret name each key of a
secrets file becomes — never a value and never a file's contents. With no
mention the scan carries a `null` `handoff`. The Find plaintext keys dialog
keeps listing the mentions for the person to update by hand and offers Copy
prompt and, where a managed agent is available, Ask an agent beside them;
`coffer credentials scan --prompt` prints the same prompt. `POST
/api/v1/credentials/import` (`coffer credentials import [--id]… [--dry-run]`)
MUST store each chosen value as `secret/<proposed name>`, confirm the store
reads back the same value, and only then replace the value in its file with the
reference, atomically and keeping the file's mode; a name already holding a
different value MUST be skipped with its file untouched; `--dry-run` writes
nothing. Each move MUST be audited as `secret_imported` without the value.

#### Scenario: a scan names plaintext secrets without their values
- **GIVEN** a `~/.coffer/secrets/db.env` holding a password and a skill whose script assigns a token
- **WHEN** the scan runs
- **THEN** both are reported with their file, key and proposed name, and the response contains neither value

#### Scenario: a skill still reading a secrets file is handed to an agent
- **GIVEN** a `~/.coffer/secrets/db.env` holding a password and a skill whose script sources that file
- **WHEN** the scan runs
- **THEN** its hand-off names the skill, the script's path and line and the file it reads, the secret names the file's keys become and how `coffer run` hands a secret to one command, and asks for the diff
- **AND** the prompt contains no value from either file, `coffer credentials scan --prompt` prints the same text, and nothing on disk has changed

#### Scenario: importing moves a value and leaves a reference
- **GIVEN** those findings
- **WHEN** they are imported
- **THEN** each value reads back from the store under its standalone name, each file now cites `coffer://secret/<name>` in place of the value with its mode unchanged, and a dry run beforehand changed nothing
