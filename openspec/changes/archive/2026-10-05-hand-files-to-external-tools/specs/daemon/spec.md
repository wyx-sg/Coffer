## MODIFIED Requirements

### Requirement: Open and reveal existing absolute paths
The daemon MUST expose filesystem-action operations: `POST /api/v1/fs/open` (open an existing
absolute path in an application — a `with` editor preference, or the OS default) and
`POST /api/v1/fs/reveal` (select / reveal an existing absolute path in the OS file manager). Both
MUST validate the path is absolute and exists before acting, MUST invoke the OS launcher with a
fixed argument vector and no shell interpolation, MUST create nothing, and MUST be guarded by the
same loopback + token auth as all other daemon routes. A non-absolute or non-existent path is
rejected (`FS_PATH_NOT_OPENABLE`, 400). Where a platform has no portable "select the file"
primitive (Linux), reveal degrades to opening the containing folder.

The daemon MUST also expose `GET /api/v1/fs/editors`, which enumerates common GUI editors detected
as installed on the host (macOS app-bundle names for `open -a`; Linux/Windows commands on `PATH`).
It returns each editor's display label and the launcher `value` accepted by `/fs/open`'s `with`,
reads nothing but app presence, and is guarded by the same loopback + token auth. It backs the
web-ui spec's preferred-editor setting, which every Open in editor uses — an agent's config files
([agent-registry](../agent-registry/spec.md) "Open config files in an external editor or reveal them"),
knowledge documents, memories, skill files and a conflicting sync file's copy — because Coffer edits
none of these files itself.

#### Scenario: a path that is not absolute is refused before anything is launched
- **GIVEN** a relative path, and an absolute path that does not exist,
- **WHEN** either is sent to `POST /api/v1/fs/open` or `POST /api/v1/fs/reveal`,
- **THEN** the request is rejected with `FS_PATH_NOT_OPENABLE` (400), no launcher process is started and nothing is created,
- **AND** `GET /api/v1/fs/editors` lists the GUI editors detected on this host, each with the launcher value that `/fs/open`'s `with` field accepts.

