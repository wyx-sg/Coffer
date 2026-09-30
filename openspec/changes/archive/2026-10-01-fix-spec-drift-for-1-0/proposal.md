## Why

The 1.0 drift audit found the specs describing storage the code no longer
has: a settings row, a vault copied before a migration, a master key beside a
database, YAML documents, a sync pointer and retry set. It found requirement
citations that no gate saw, because they used spec-internal forms the
citation gate did not read, and surfaces with no requirement at all: the
vault's recent-changes and refused-hand-edit lists, the git 2.40 minimum and
the channel detail page's tabs. Two refusals put a hard-coded installer in
front of the person, and the API schema and its doc pages answered without
the token.

## What Changes

- internal-engine: "Keep the engine's settings in one global row" becomes
  "Keep the engine's settings in one vault document", and every scenario that
  said "row" says "document".
- daemon: "Deploy frozen sibling binaries and back up the vault before
  migrating" becomes "… back up the history database before migrating"; its
  scenario is "a schema upgrade keeps a copy of the history database". The
  token requirement also covers `GET /api/v1/openapi.json`, and the daemon
  serves no `/docs` or `/redoc` pages.
- vault-storage: two new requirements, "List recent vault changes and the hand
  edits kept out" (`GET /api/v1/vault/changes`, `GET /api/v1/vault/problems`,
  `coffer vault problems`) and "Refuse to start on a git older than 2.40",
  whose refusal carries an agent hand-off instead of an installer.
- channels: the detail page's Overview and Settings tabs are part of "Manage
  channels from the Channels page and the CLI".
- vault-sync: `coffer sync remote check` sends the user name the token goes
  with (`--username`, else the stored remote's), like saving does. Scenario
  "a round diffs from the pointer stored on this machine" becomes "a round
  diffs from the shared history"; the coffer-guide render no longer claims to
  depend on reach; the principles' Local-First rule replaces "constitution".
- secret, memory, knowledge, web-ui, channels/seatalk: storage wording, two
  scenario renames ("keep partitions as resource files and plain files only",
  "a collection is a resource file and a directory, nothing more") and three
  stale citations.
- Data models, the memory contract's derived-root path and code comments
  follow; the desktop app's no-daemon message points at the install page and
  an agent prompt instead of a piped install script.
- Gates: `check_spec_citations.py` also reads relative `spec.md` links and
  `see "<Title>"` inside the specs; `check_removed_commands.py` scans
  `README.zh-CN.md`, `docs/` (ADRs excepted) and `desktop/src`; a new
  `check_error_codes_reference.py` holds the error-code pages (en and zh) to
  the daemon's status table.

## Capabilities

### New Capabilities

### Modified Capabilities

- `channels`
- `channels/seatalk`
- `daemon`
- `internal-engine`
- `knowledge`
- `memory`
- `secret`
- `vault-storage`
- `vault-sync`
- `web-ui`

## Impact

The daemon's app factory and a new schema route module, the vault
composition root and the git hand-off, `coffer sync remote check`, the desktop
shell's resolver, three gates under `scripts/` and their tests, the
error-code and CLI reference pages, and comments across the backend, the
desktop shell and the frontend.
