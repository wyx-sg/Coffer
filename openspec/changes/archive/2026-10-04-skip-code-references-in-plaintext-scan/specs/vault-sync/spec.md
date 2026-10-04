## MODIFIED Requirements

### Requirement: Refuse to push a plaintext secret
Before a round pushes — a round that merged, a push with nothing to pull, or a join — it MUST read
every file version the push would publish: each blob reachable from the commit being pushed and
not from the remote's head, from every commit in between. It reads them for an assignment whose name says secret and for the well-known token shapes.
An unquoted value that is code names a value rather than holding one, and MUST NOT be reported:
a value holding call, index or list punctuation (`(`, `)`, `[`, `]`, `,`, `;`), so
`token = m.group(0)` or `password=password,` is not reported; names joined by `.` or `?.`, each
made of letters and underscores with digits only at its end, such as an environment-variable read
or a member (`process.env.SPACE_TOKEN`, `args.token`, `page.next_page_token`); and a bare name a
declaration (`const`, `let`, `var`, `final`, `val`, `auto`) or a member assignment (`self.`,
`this.`, `cls.`) gives. A JSON Web Token (`eyJ…`) and a dotted value whose parts mix digits in are
values. A quoted value is always a value, and a well-known token shape (`ghp_`, `github_pat_`,
`sk-`, `xoxb-` and its siblings, `AKIA`) MUST be reported wherever it sits on the line, code around
it or not.
An encrypted `secret/<ref>.enc` file is ciphertext and MUST NOT be read; a binary file or one over
1 MB is not read either.

When a file still holds a value at the commit being pushed, the round MUST push nothing and record
the status `plaintext_found`. The record's `plaintext` names each place: the file, the line, and
the name the value is assigned to (`token` for a value recognised by its shape alone). Nothing the
round records, reports or hands off carries the value. The status's `problem` is
`plaintext_found`, with the places and an agent hand-off. The hand-off asks for each value to be
moved into a Coffer secret and the file pointed at it, without printing the value, and it leaves
Retry to the person. The attention list carries the `sync_plaintext_found` item with the same
hand-off.

When only an earlier, unpushed commit holds a value, because the file was fixed since, the round
MUST NOT publish that commit. It folds the unpushed commits into one commit on the remote's head,
with the same files, checks it out in their place, and pushes that. It records how many commits it
folded as `folded`. No file on disk changes.

"Push anyway" (`POST /api/v1/sync/plaintext/push-anyway`) MUST allow
exactly the file versions the last round found, record the audit event `sync_plaintext_pushed`
with the files and lines, and run a round. A file changed since is a new version and is read
again. When the last round is not `plaintext_found`, it MUST be refused with
`SYNC_NO_PLAINTEXT_FOUND` (409).

#### Scenario: a plaintext secret stops the round before anything is pushed
- **GIVEN** a joined machine whose knowledge document gains the line `DB_PASSWORD=<a value>`
- **WHEN** a round runs, and the status and the attention list are read
- **THEN** the round is `plaintext_found`, the remote's head has not moved and holds no copy of the value, and the other machine never receives the file
- **AND** each surface names the document, line 4 and `DB_PASSWORD`, the prompt asks for the value to be moved with `coffer secret set`, and none carries the value

#### Scenario: a value removed before the push is not published from the history
- **GIVEN** a round stopped as `plaintext_found`, after which the person replaces the value with a `coffer://secret/` reference and makes another edit
- **WHEN** the next round runs
- **THEN** it pushes one folded commit on the remote's head, recording how many commits it folded
- **AND** the remote holds no object containing the value, and the other machine receives both edits

#### Scenario: push anyway allows exactly what was found and is audited
- **GIVEN** a machine whose last round did not find a plaintext secret
- **WHEN** Push anyway is asked for, then a round stops as `plaintext_found` and Push anyway is asked for again
- **THEN** the first is refused with `SYNC_NO_PLAINTEXT_FOUND`, the second pushes the file and records `sync_plaintext_pushed` naming the file and line
- **AND** a new value written into the same file stops the next round again

#### Scenario: an encrypted secret file is not read
- **GIVEN** a remote that carries secret ciphertext, and a `secret/<ref>.enc` file whose bytes look like a token
- **WHEN** a round runs
- **THEN** it pushes the file

#### Scenario: the Sync page names each place and offers the hand-off and push anyway
- **GIVEN** the Sync page with a `plaintext_found` problem
- **WHEN** it is shown
- **THEN** its card lists each file, line and key a file still holds, with the agent hand-off that moves each value into a secret, and no Retry
- **AND** Push anyway runs only after a confirmation that says it is recorded in the audit log

#### Scenario: code that reads a secret from elsewhere is not a plaintext secret
- **GIVEN** a skill script with `const token = process.env.SPACE_TOKEN || require(…)`, `token = args.token or os.environ.get(…)`, `token=page.next_page_token;` and `const token = accessToken`
- **WHEN** it is read for plaintext secrets
- **THEN** nothing is reported
- **AND** a quoted literal, a `.env`-style `API_KEY=` value, a JSON Web Token, and a `ghp_` token beside `process.env.SPACE_TOKEN ||` on the same line still are

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
- **GIVEN** a document the remote already holds with the line `API_KEY=my-example-key-123`, pushed anyway, to which this machine adds a line with a GitHub token
- **WHEN** a round stops as `plaintext_found` and each place's context is asked for
- **THEN** the old line is `modified`, already on the remote, and hinted as a placeholder holding `example`, and the token keeps only `ghp_` visible
- **AND** the masked diff adds one line and carries no value

#### Scenario: the Sync page opens each place to its masked lines
- **GIVEN** the Sync page with a `plaintext_found` problem
- **WHEN** a place is opened
- **THEN** it shows the masked lines with the flagged one marked, whether the file is new or changed, and the value's shape in words
- **AND** for a changed file "Show changes" shows the masked diff
