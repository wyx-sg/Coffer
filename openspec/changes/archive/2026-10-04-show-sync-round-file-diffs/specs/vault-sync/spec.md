## ADDED Requirements

### Requirement: Show what a round changed in each file
The round drawer MUST let a person open any file the round **applied** here or
**pushed** and read what changed in it, line by line, without storing anything
new: `GET /api/v1/sync/runs/{id}/diff?path=<file>&side=applied|pushed` MUST
compute a unified diff from the vault's git history. For `applied` it compares
this machine's version before the round with its version after; for `pushed` it
compares the remote tip the push went on top of with the pushed commit. The
response MUST carry a `kind`: `text` with the diff and its added and removed line
counts; `secret` for a file under `secret/`, with no content at all, not even
ciphertext; `binary` for a file that is not text; `too_large` for a file or diff
over the size cap. A `path` the round did not list on that side MUST be refused
(`SYNC_ROUND_FILE_NOT_LISTED`, 404), so the endpoint never reads an arbitrary
file; a round whose commits are no longer in the vault MUST answer
`SYNC_ROUND_DIFF_UNAVAILABLE` (409). The drawer MUST show each file as a row
that expands to the diff (old and new line numbers, added and removed lines
tinted) with the counts beside the file once loaded, and a plain message for
each non-text kind. Pulled commits MUST NOT carry a diff.

#### Scenario: an applied file shows its line-by-line diff
- **GIVEN** a round that applied another machine's edit to a knowledge document
- **WHEN** the file is asked for with `side=applied`
- **THEN** the diff holds the removed and the added lines of that edit and their counts

#### Scenario: a pushed file shows its line-by-line diff
- **GIVEN** a round that pushed this machine's edit to a knowledge document
- **WHEN** the file is asked for with `side=pushed`
- **THEN** the diff is against the version the remote held before the push

#### Scenario: a secret file shows no content
- **GIVEN** a round that pushed an encrypted file under `secret/`
- **WHEN** the file is asked for
- **THEN** the answer is `kind: "secret"` with no diff, and the drawer says the contents are not shown

#### Scenario: a path the round did not touch is refused
- **GIVEN** a round and a vault file it neither applied nor pushed
- **WHEN** that file is asked for on either side
- **THEN** the answer is `SYNC_ROUND_FILE_NOT_LISTED`

#### Scenario: expanding a file in the drawer shows its diff
- **GIVEN** the drawer of a round that applied a file
- **WHEN** the file's row is expanded
- **THEN** its diff rows and its added and removed counts appear
