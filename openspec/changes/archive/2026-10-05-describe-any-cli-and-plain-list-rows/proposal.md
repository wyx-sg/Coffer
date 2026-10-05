## Why

The Secrets and Skills lists put each description under the name, and with a
library of a dozen rows the second lines crowd the list until no name stands out.
A command-line tool, meanwhile, could carry a description only if the person added
it by hand; the tools that skills and MCP servers require — most of the page —
had nowhere to say what they are for.

## What Changes

- A Secrets list row shows the secret's name alone; its description stays in the
  detail's header, where it is edited, and search still matches it.
- A Skills library row shows the skill's name alone, with a second line only when
  something needs the reader.
- Every CLI's page carries its description under the header, edited in place.
  `PATCH /api/v1/clis/{command}` with only `description` keeps it for any listed
  command, in the `cli-tools` vault document under `notes`.

## Capabilities

### Modified Capabilities

- `skill-manager`: a required tool takes a description.
- `web-ui`: list rows lose their description line; the CLI page edits a description in place.

## Impact

`cli_tools.py`, `cli_tool_repo.py`, `cli_status.py`, the CLI routes and contract;
`SecretListRow`, `SkillLibraryRow`, `CliHeader` and a new `CliDescriptionField`.
