## MODIFIED Requirements

### Requirement: Declare a command-line tool without a skill
The system MUST let a person add a command-line tool by hand, with no skill and
no MCP server behind it: `POST /api/v1/clis` takes a bare command name or the
absolute path of an executable, and optionally a `title`, a `description`, a
`min_version` and a `login_check` (a command line whose first word is the
command itself, run without a shell exactly as a skill's login check is). The
tool is kept as one entry in the vault's `cli-tools` state document — the
declaration only; where the command is found on one machine is machine-local and
never written there — and is then listed, checked and read like every required
command, with `added` true. When a skill or an MCP server also requires the
command the two are one entry, the hand-added title, description and minimum
taking precedence. `POST /api/v1/clis/preview` MUST report what Coffer finds for
a name or path before anything is saved — where, which version, whether it was
already added and whether a skill or server already requires it — and a tool that
is not on this machine MUST still be addable, then reading `missing`. A tool
added by hand and missing raises no attention item, because nobody asked for it
to work. `PATCH /api/v1/clis/{command}` changes the fields it carries (`null`
clears one; the command itself is fixed) and `DELETE /api/v1/clis/{command}`
drops the declaration only — a skill or server that requires the command keeps
it listed — and both refuse a command nobody added by hand with 404
`CLI_TOOL_NOT_DECLARED`, except that `PATCH` carrying only `description` MUST
keep that description for any listed command: a command a skill or server
requires is not the person's to declare, but what it is for is theirs to write.
Such a description is kept in the same `cli-tools` document, under `notes`, and
a hand-added tool's own description wins over it; a command nobody lists is
refused with 404 `CLI_NOT_KNOWN`. A name added twice is refused with 409
`CLI_TOOL_EXISTS`, and a bad name, path, minimum version or login check with 400
`CLI_TOOL_INVALID`. Each add, edit and removal MUST be audited. Coffer MUST NOT
read a command's `--help`, build a tree of its subcommands or keep one: what it
knows of a tool is its path, its version and its login state.

#### Scenario: a command-line tool is added with no skill
- **GIVEN** no skill and no MCP server requiring `jq`, and `jq 1.7.1` on the path
- **WHEN** the user adds `jq` with a title, a description and the minimum `1.6`
- **THEN** `GET /api/v1/clis` lists `jq` as `ready`, added by hand, needed by nobody, and the vault's `cli-tools` document holds the declaration and no path
- **AND** adding it again is refused with `CLI_TOOL_EXISTS`, and a minimum of `latest` with `CLI_TOOL_INVALID`

#### Scenario: a hand-added tool and a skill are one entry
- **GIVEN** a skill requiring `jq` with minimum `1.5`, and `jq` added by hand with the title `Mine` and minimum `1.7`
- **WHEN** the commands are listed, and then the hand-added declaration is removed
- **THEN** one entry `jq` is listed, titled `Mine` with minimum `1.7` and needed by the skill
- **AND** after the removal it is still listed, no longer added by hand, with the skill's title and minimum `1.5`

#### Scenario: add, edit and remove a tool over REST
- **GIVEN** `jq` on the path and no declaration
- **WHEN** the user adds `jq` with the title `JSON`, then sends `PATCH /api/v1/clis/jq` with the title `null`, then `DELETE /api/v1/clis/jq`
- **THEN** the tool is listed as added by hand after the first, its title is cleared by the second, and it is gone after the third
- **AND** repeating the delete is refused with 404 `CLI_TOOL_NOT_DECLARED`

#### Scenario: a required tool takes a description and nothing else
- **GIVEN** a skill requiring `jq` and no declaration
- **WHEN** the user sends `PATCH /api/v1/clis/jq` with only a description, then one with a title, then one describing a command nobody lists
- **THEN** `jq` reads that description, still not added by hand, and the vault's `cli-tools` document keeps it under `notes`
- **AND** the title is refused with 404 `CLI_TOOL_NOT_DECLARED` and the unknown command with 404 `CLI_NOT_KNOWN`
