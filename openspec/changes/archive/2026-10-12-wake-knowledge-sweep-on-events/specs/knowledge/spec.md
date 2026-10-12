## MODIFIED Requirements

### Requirement: Sweep the knowledge root on its mechanical duties
The daemon MUST run a **knowledge sweep** when a file under `knowledge/` changes and otherwise every 10 minutes ([daemon](../daemon/spec.md) "Wake background workers on events and park them without demand"), and the sweep MUST do exactly these things and call no model: adopt every file sitting in a collection's `.inbox/` as a source (see "Adopt a file dropped into the inbox"); file every Markdown document left in a collection outside `pages/`, `sources/` and hidden entries, other than the root `README.md`, and untouched for a minute (a document still inside that minute is revisited once it is over), into `pages/` at the same relative path, suffixed on a collision, as one commit by the daemon that rewrites no content; commit every change found on disk under `knowledge/` as an edit on disk, so a person's editor or an agent's file tools is never counted as Coffer's (see "Commit every knowledge write naming its writer"); and re-render and re-seed the `coffer-guide` skill so a page added by hand is catalogued. The sweep MUST NOT hold the vault against a sync round: whatever it writes goes through the vault's ordinary writer. While the `knowledge` feature is switched off the sweep MUST skip its rounds ([experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces").

#### Scenario: a sweep catalogues a document added by hand
- **GIVEN** a collection and a Markdown page a person adds under its `pages/` in their own editor
- **WHEN** the knowledge sweep runs
- **THEN** the page is committed as an edit on disk and the re-rendered guide's catalogue lists it

#### Scenario: a sweep promotes a file dropped into the inbox
- **GIVEN** a Markdown file dropped into `shopee/.inbox/`
- **WHEN** the knowledge sweep runs
- **THEN** the file is a source under `shopee/sources/` and `.inbox/` no longer holds it

#### Scenario: a sweep files a loose document into pages
- **GIVEN** a collection holding `infra/cache.md` and `notes.md` outside `pages/` and `sources/`, both untouched for over a minute, and a `README.md` at its root
- **WHEN** the knowledge sweep runs
- **THEN** they are `pages/infra/cache.md` and `pages/notes.md` with their text unchanged, moved in one commit by the daemon, and the README has not moved

#### Scenario: a sweep runs while a sync round waits
- **GIVEN** a sync round that waits for a person and a file in an inbox
- **WHEN** the knowledge sweep runs
- **THEN** it does not wait for the round, and the file is adopted through the vault's ordinary writer

#### Scenario: a switched-off knowledge feature skips the sweep
- **GIVEN** the `knowledge` feature switched off and a file in an inbox
- **WHEN** the sweep runs
- **THEN** nothing is adopted, moved, committed or re-rendered, and the collections stay on disk untouched
