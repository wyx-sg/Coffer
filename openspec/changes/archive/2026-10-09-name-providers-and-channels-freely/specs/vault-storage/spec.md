## MODIFIED Requirements

### Requirement: Keep every vault document a JSON object that preserves what it does not know
Every document Coffer parses in the vault — resource files, state documents,
machine descriptors — SHALL be a JSON object written with one deterministic
encoding (two-space indent, a trailing newline, keys in the order the file
already has them), so a write that changes nothing makes no commit. A reader
SHALL validate the fields it knows and keep every other top-level field
verbatim, in place, on every write; an unknown top-level field MUST be
reported as a warning and MUST NOT be refused. A resource file's `config` is
its kind's and SHALL hold only the keys the kind's schema declares: a file
whose config holds any other key, and a name the kind's name rule refuses (free text for a provider or a channel, a slug for every other kind), MUST be refused with a finding naming it — the same rules a registration
through the API meets — whether a person wrote the file or a sync merge
brought it.

#### Scenario: a document round-trips to the same bytes
- **GIVEN** a resource file written by Coffer
- **WHEN** it is read and written back unchanged
- **THEN** its bytes are identical and no commit is made

#### Scenario: a field this build does not know survives a write
- **GIVEN** a resource file carrying a top-level field this build does not know
- **WHEN** Coffer changes the resource's config
- **THEN** the field is still in the file, in the same place, with the same value

#### Scenario: a config key the kind does not declare is refused
- **GIVEN** a registered resource
- **WHEN** a person adds a config key its kind does not declare to its file
- **THEN** the edit is not committed and a finding names the key
- **AND** the resource keeps its last valid config

### Requirement: Identify a resource by the uid inside its file
A resource file SHALL carry its `uid`, `kind`, `format_version`, `name`,
`description` and `config` (and `created_at` where set); the path is
where Coffer filed it (`resources/<kind>/<name>.json`, or `resources/<kind>/<uid>.json` for a provider and a
channel, whose names are free text) and nothing SHALL key on the path. A file without a `uid` SHALL be taken as a new resource and given
one by a daemon commit. When two paths claim one uid, the path that did not
hold it at `HEAD` MUST be refused and flagged, and the original MUST stay in
effect. The reasoning is
[A Resource's Identity Is the `uid` Inside Its File](../../../docs/decisions/identity-is-the-uid-inside-the-file.md).

#### Scenario: a copied resource file is flagged and the original is untouched
- **GIVEN** a registered resource and a person's copy of its file under another name
- **WHEN** the vault settles the copy
- **THEN** the copy is not committed and is flagged as a duplicate of the original's path
- **AND** the original resource is unchanged

#### Scenario: a hand-made resource file is given a uid
- **GIVEN** a person writes a valid resource file with no `uid`
- **WHEN** the vault settles it
- **THEN** the person's file is committed as a disk edit and a daemon commit then adds a freshly minted uid

#### Scenario: moving a resource file keeps the resource
- **GIVEN** a registered resource
- **WHEN** a person moves its file to another name in the same kind directory
- **THEN** the resource keeps its uid, its reach and everything that references it
