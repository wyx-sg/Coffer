## Why

The Edit dialog of a CLI a skill or MCP server requires offered only the description, while
the Add CLI form it reuses has a display name, minimum version and login check too. People
expect to change everything the form shows, whoever declared the tool.

## What Changes

- `PATCH /api/v1/clis/{command}` takes every field on a required tool too, kept as the
  person's edits in the `cli-tools` document (`notes` for the description, `edits` for the
  rest). They win over what the skills say, as a hand-added declaration's would; `null`
  brings the skills' value back. The tool stays not added by hand.
- The Edit dialog shows every field for every CLI, filled with what it reads now; for a
  required one it sends only what changed and says how edits layer over the skills'.

## Impact

- Backend: CLI tool service, `cli-tools` repository, required-command aggregation.
- Frontend: Add CLI dialog. Specs: skill-manager, web-ui. Docs: CLIs guide (en + zh).
