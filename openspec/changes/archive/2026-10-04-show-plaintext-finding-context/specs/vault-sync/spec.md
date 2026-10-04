## ADDED Requirements

### Requirement: Show a plaintext finding in its file
The Sync page MUST let a person read each place a `plaintext_found` round
listed in its file, so they can judge whether it is a secret, without Coffer
ever returning the value. `GET /api/v1/sync/plaintext/context?path=<file>&line=<n>`
MUST compute, from the file version the last round found the value in and
without storing anything: the flagged line with up to three lines either side,
each with every plaintext value on it masked; whether the remote already holds
the file (`added` or `modified`) and the flagged line; and for a `modified`
file within the size cap, its unified diff against the remote's copy with
every line masked the same way, and its added and removed counts.

Masking MUST replace every character of a value with `•`, keeping the line's
length, except a well-known token format's public prefix (`ghp_`,
`github_pat_`, `sk-`, `xoxb-` and its siblings, `AKIA`) or a URL's scheme.
Each masked value MUST carry its place on the line, the name it is assigned
to, and its shape: its length, which kinds of character it holds (lower,
upper, digit, symbol), that prefix, and a hint — `reference` for names joined
by dots, `placeholder` with the placeholder word it holds, `repeated` for one
or two characters over and over. No other character of a value MAY appear in
the response, and the response MUST NOT be stored, logged or audited.

When the last round is not `plaintext_found` the request MUST be refused with
`SYNC_NO_PLAINTEXT_FOUND` (409); a place the round did not find in a current
file MUST be refused with `SYNC_PLAINTEXT_NOT_LISTED` (404), so the route never
reads an arbitrary file. The plaintext card MUST show each place as a row that
expands to the masked lines — line numbers, the flagged line tinted, each
masked value highlighted — with whether the file is new or changed, whether the
line is already on the remote, the value's shape in words, and for a changed
file the masked diff behind "Show changes".

#### Scenario: a finding is shown in its file with the value masked
- **GIVEN** a round stopped as `plaintext_found` on line 4 of a new knowledge document, with another value on line 5
- **WHEN** the place's context is asked for, before and after the round, and for a line the round did not find
- **THEN** before the round it is `SYNC_NO_PLAINTEXT_FOUND`, and after it lines 1 to 7 come back with both values masked to `•` of the same length, the file `added`, and line 4's value keyed `DB_PASSWORD` with its length and kinds of character
- **AND** neither value appears in the response, and a line the round did not find is `SYNC_PLAINTEXT_NOT_LISTED`

#### Scenario: a finding in a file the remote holds shows its masked change
- **GIVEN** a document the remote already holds with the line `const token = process.env.ORDERS_TOKEN`, to which this machine adds a line with a GitHub token
- **WHEN** a round stops as `plaintext_found` and each place's context is asked for
- **THEN** the old line is `modified`, already on the remote, and hinted as a code reference, and the token keeps only `ghp_` visible
- **AND** the masked diff adds one line and carries no value

#### Scenario: the Sync page opens each place to its masked lines
- **GIVEN** the Sync page with a `plaintext_found` problem
- **WHEN** a place is opened
- **THEN** it shows the masked lines with the flagged one marked, whether the file is new or changed, and the value's shape in words
- **AND** for a changed file "Show changes" shows the masked diff
