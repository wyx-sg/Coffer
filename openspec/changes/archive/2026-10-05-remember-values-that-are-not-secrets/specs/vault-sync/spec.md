## MODIFIED Requirements

### Requirement: Refuse to push a plaintext secret
Before a round pushes — a round that merged, a push with nothing to pull, or a join — it MUST read
every file version the push would publish: each blob reachable from the commit being pushed and
not from the remote's head, from every commit in between. It reads them with the detector the
Secrets page's scan uses ([secret](../secret/spec.md) "Detect plaintext secrets with the bundled rules").
An unquoted value that is code names a value rather than holding one, and MUST NOT be reported:
a value holding call, index or list punctuation (`(`, `)`, `[`, `]`, `,`, `;`), so
`token = m.group(0)` or `password=password,` is not reported; names joined by `.` or `?.`, each
made of letters and underscores with digits only at its end, such as an environment-variable read
or a member (`process.env.SPACE_TOKEN`, `args.token`, `page.next_page_token`); and a bare name a
declaration (`const`, `let`, `var`, `final`, `val`, `auto`) or a member assignment (`self.`,
`this.`, `cls.`) gives. A JSON Web Token (`eyJ…`) and a dotted value whose parts mix digits in are
values. A value a rule recognises by its format (`ghp_`, `github_pat_`, `sk-`, `xoxb-` and its
siblings, `AKIA`, and every other vendor format the bundled rules know) MUST be reported wherever it
sits on the line, code around it or not.
An encrypted `secret/<ref>.enc` file is ciphertext and MUST NOT be read; a binary file or one over
1 MB is not read either.

When a file still holds a value at the commit being pushed, the round MUST push nothing and record
the status `plaintext_found`. The record's `plaintext` names each place: the file, the line, the
name the value is assigned to (the rule's id for a value with no name before it), and the rule that
found it. Nothing the
round records, reports or hands off carries the value. The status's `problem` is
`plaintext_found`, with the places. A plaintext secret MUST NOT be handed to an agent: neither the
problem nor the attention list's `sync_plaintext_found` item carries a hand-off prompt, because the
prompt would send an agent to the file that holds the value. The Sync page's card offers two
actions, and no Retry: "Move into secrets…" opens the Secrets page's move (spec secret "Move
plaintext secrets in managed resources into the store") in place, listing the findings in the
flagged files alone; a flagged file it cannot move a value out of — anything but a skill's file —
is left for the person to edit, and when none of the flagged files is one, the dialog says so.
After the move the person syncs again, and the round reads the rewritten files.

When only an earlier, unpushed commit holds a value, because the file was fixed since, the round
MUST NOT publish that commit. It folds the unpushed commits into one commit on the remote's head,
with the same files, checks it out in their place, and pushes that. It records how many commits it
folded as `folded`. No file on disk changes.

A value this machine was told is not a secret ([secret](../secret/spec.md) "Remember a value a
person says is not a secret") MUST NOT stop a round, wherever it sits and whatever else in its
file changed.

"Push anyway" (`POST /api/v1/sync/plaintext/push-anyway`) MUST allow
exactly the file versions the last round found, remember each value the last round found as not a
secret, record the audit event `sync_plaintext_pushed` with the files and lines, and run a round.
A later edit to the same file is read again, but stops a round only for a value not remembered.
When the last round is not `plaintext_found`, it MUST be refused with
`SYNC_NO_PLAINTEXT_FOUND` (409).

#### Scenario: a plaintext secret stops the round before anything is pushed
- **GIVEN** a joined machine whose knowledge document gains the line `DB_PASSWORD=<a value>`
- **WHEN** a round runs, and the status and the attention list are read
- **THEN** the round is `plaintext_found`, the remote's head has not moved and holds no copy of the value, and the other machine never receives the file
- **AND** each surface names the document, line 4, `DB_PASSWORD` and its rule, none carries the value, and none carries an agent hand-off

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

#### Scenario: a value pushed anyway does not stop a later edit of its file
- **GIVEN** a round stopped as `plaintext_found` on a note, and Push anyway
- **WHEN** the person edits another line of the note, and a round runs
- **THEN** the round pushes the note
- **AND** when the value itself is changed, the next round stops as `plaintext_found` again

#### Scenario: an encrypted secret file is not read
- **GIVEN** a remote that carries secret ciphertext, and a `secret/<ref>.enc` file whose bytes look like a token
- **WHEN** a round runs
- **THEN** it pushes the file

#### Scenario: the Sync page names each place and offers Move into secrets and push anyway
- **GIVEN** the Sync page with a `plaintext_found` problem in a skill's script and a knowledge document
- **WHEN** it is shown, and Move into secrets… is chosen
- **THEN** its card lists each file, line, key and rule a file still holds, with Move into secrets… and Push anyway…, and no agent hand-off and no Retry
- **AND** the move lists only the skill script's finding and moves it through a reviewed dry run, a dialog opened on files it cannot move from says so, and Push anyway runs only after a confirmation that says it is recorded in the audit log and that this machine will not stop on those values again

#### Scenario: code that reads a secret from elsewhere is not a plaintext secret
- **GIVEN** a skill script with `const token = process.env.SPACE_TOKEN || require(…)`, `token = args.token or os.environ.get(…)`, `token=page.next_page_token;` and `const token = accessToken`
- **WHEN** it is read for plaintext secrets
- **THEN** nothing is reported
- **AND** a quoted literal, a `.env`-style `API_KEY=` value, a JSON Web Token, and a `ghp_` token beside `process.env.SPACE_TOKEN ||` on the same line still are

#### Scenario: a vendor token in a knowledge note stops the round
- **GIVEN** a joined machine whose knowledge note gains a Stripe secret key on a line of prose, assigned to no name
- **WHEN** a round runs
- **THEN** the round is `plaintext_found`, naming the note, the line and `stripe-access-token`, and nothing is pushed

#### Scenario: a resource document's secret references do not stop a push
- **GIVEN** a joined machine that registers an MCP server whose document cites two secrets in `secret_refs`
- **WHEN** a round runs
- **THEN** it pushes the document
