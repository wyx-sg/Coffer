## Why

A CLI's page edited its description in place, in an always-there field under the header
that read "What this tool is for" when empty, unlike every other detail page, which edits
through Edit and a dialog. Only a CLI added by hand had Edit at all. The Add CLI form also
labelled the tool's display name "Title" beside "Description", which read as the same
thing twice.

## What Changes

- The CLI page's header shows the description as text, and nothing when there is none.
- Every CLI has Edit, which opens the Add CLI form with the command locked; for a CLI only a
  skill or MCP server requires it edits the description alone. Remove stays in the ⋯ menu
  of a CLI added by hand.
- The form's "Title" field is labelled "Display name", with an example (`GitHub CLI`) as
  its placeholder. The wire field stays `title`, as in a skill's `requires:`.

## Impact

- Frontend: CLI header, CLI actions, Add CLI dialog; the in-place description field goes.
- Specs: web-ui. Docs: CLIs guide (en + zh).
