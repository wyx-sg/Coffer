## MODIFIED Requirements

### Requirement: Expose the master key's location on every surface
Users MUST be able to read and change the key's location from the management API
(`GET`/`PUT /api/v1/settings/secrets`) and from a Settings card that states the consequence and
confirms before it writes. `secrets.storage` is not one of the keys read before the daemon binds,
so `coffer config` does not carry it (see [resource-framework](../resource-framework/spec.md),
"Keep the command line to what needs it"). `PUT /api/v1/settings/secrets` MUST refuse any value
other than `file` or `keychain` as a validation error, and a change MUST run the verified relocation
of "Verify the destination before relocating the master key".

#### Scenario: read and change the master key location from the API and the command line
- **GIVEN** a running daemon whose master key is in the file `~/.coffer/master.key`
- **WHEN** the location is read with `GET /api/v1/settings/secrets` and on the Settings card, then changed to the keychain with `PUT /api/v1/settings/secrets`
- **THEN** both reads report the file location
- **AND** after the change both surfaces report the keychain, and a previously stored secret still reads back

#### Scenario: move the master key with the config command
- **GIVEN** a running daemon whose master key is in the file `~/.coffer/master.key`
- **WHEN** the user picks the keychain on the Settings card and confirms, and then `PUT /api/v1/settings/secrets` is sent the value `vault`
- **THEN** the first moves the key to the keychain, audited as `master_key_relocated`, and a previously stored secret still reads back
- **AND** the second is refused as a validation error naming the accepted values and leaves the key where it is

### Requirement: Delete a secret idempotently
`DELETE /api/v1/secrets/{ref}` MUST be idempotent, answer `204` whether or not the ref was
present, and record a `secret_deleted` audit entry when it removed something.

#### Scenario: delete a secret frees the reference
- **GIVEN** a secret `{ref}` exists and is cited by zero MCP servers,
- **WHEN** the user issues `DELETE /api/v1/secrets/{ref}` (the Secrets page's Delete button),
- **THEN** the ciphertext file is removed, the deletion is audited, and a later registration may reuse `{ref}` without conflict.

### Requirement: Route every secret command through the daemon
Every secret command MUST go through the daemon's API and MUST import no secret or keyring
code of its own. This covers the `coffer secret` group and `coffer config`, which carries no secrets
setting. The daemon is the sole owner of the key, and a CLI that opened the keychain itself
would be a second reader to keep honest.

#### Scenario: secret commands import no secret code
- **GIVEN** the `coffer secret` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the secrets infrastructure package
- **AND** it reaches the vault only through the daemon client

#### Scenario: the config command reaches the master key only through the daemon
- **GIVEN** the `coffer config` command module
- **WHEN** its imports are inspected
- **THEN** it imports neither `keyring` nor any module of the secrets infrastructure package
- **AND** it has no `secrets.storage` key, so the master key's location is changed only through the daemon's settings route

### Requirement: Carry references, never secrets, in resource configuration
A resource's configuration MUST carry secret references and never secret values. Each kind
declares how its refs are extracted from its own config shape; a kind that declares no extractor
cites no secrets and is never probed. A reference is resolved only at the moment of use.

#### Scenario: store and reference a secret
- **GIVEN** the user has not yet stored an HTTP secret,
- **WHEN** the user issues `POST /api/v1/secrets` (the Secrets page's Add button, or `coffer secret set`) with `ref` and the secret `value` in the request body, then registers an HTTP MCP server whose `secret_refs` cites `{ref}`,
- **THEN** the secret value is written only as Fernet ciphertext in its file under `vault/secret/` (its plaintext never reaches any file, the history database, any log, or the audit), and the server registration succeeds with the secret resolved (decrypted) at upstream-spawn time.

### Requirement: Return no plaintext on any route, command or tool
No management route, `coffer` command or MCP tool MUST return a secret's
plaintext or the master key, with two exceptions this spec names: the desktop
app's presence-gated reveal and key backup (see "Release plaintext only to a
present human in the desktop app"), and `coffer run`'s resolve of standalone
secrets (see "Resolve standalone secrets into one child with coffer run").
There is no `GET /api/v1/secrets/{ref}` and no `POST /api/v1/sync/key/export`, and no
`coffer` command prints a stored value.
Writing a secret stays open to every surface: a caller that supplies a value
already has it. An audit row is not a refusal — a path that returns a value is
a defect however it is audited
([Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).

#### Scenario: no route or command hands out a stored value
- **GIVEN** a running daemon holding a secret under a ref
- **WHEN** a caller with the daemon's token asks `GET /api/v1/secrets/{ref}` and `POST /api/v1/sync/key/export`, and a person runs `coffer secret list`
- **THEN** each route is refused as one that does not exist, and the list names the ref without its value
- **AND** no response or output carries the value or the master key

### Requirement: Hold a secret for a new destination until a person approves it
A destination is a place Coffer sends a secret's plaintext: an MCP server's
environment variable or HTTP header, a channel adapter's secret, the sync
remote's push token, and — through the same service call — a provider
connection's key and a custom tool's authentication. Every consumer MUST name
the destination and the **target** that receives the value (a stdio server's
whole command line with its working directory and non-secret environment, an
HTTP URL, a git URL, a channel's platform and app) before it resolves a secret,
and MUST inject nothing into a target no person approved: the attempt answers
`SECRET_BINDING_PENDING` (409) naming the pending approvals, or
`SECRET_BINDING_REJECTED` (409) naming a refused one (nothing waits, and it
stays refused for that target until the destination changes). Citing an existing
secret from a destination that did not cite it, and changing the target of one
that did, each record a pending approval, once per target; a later target
supersedes the approval for the earlier one. A binding already approved for
its target MUST keep working. A binding is approved without a person only when
its value was supplied for it — the destination was just registered or changed,
and the ref was never bound anywhere, is not a standalone `secret/` name and
was written on this machine within the last five minutes (see "Approve a secret's binding when its
destination is registered") — or while the protection is switched off.
Approving MUST
take a presence grant (`POST /api/v1/secrets/approvals/{id}/approve`, or several at once
under "Approve several bindings in one confirmation");
refusing (`POST .../reject`) MUST NOT, and records its audit event. `GET /api/v1/secrets/approvals`
lists approvals, having first evaluated every current destination, and marks
superseded those nothing asks for any more.

#### Scenario: citing an existing secret from a new MCP server waits for approval
- **GIVEN** a secret an MCP server is already approved to receive
- **WHEN** a second MCP server citing the same ref is registered, and a session reaches its tools
- **THEN** the second server is not spawned with the secret, the attempt answers `SECRET_BINDING_PENDING`, and one pending approval names the ref, the new server and its command line
- **AND** the first server keeps receiving the secret

#### Scenario: a refused binding stays refused until its target changes
- **GIVEN** a pending approval for a server's secret that a person rejects
- **WHEN** the server is next started or listed, and then its target changes
- **THEN** the first answers `SECRET_BINDING_REJECTED` (409, a refusal, not a wait) and the web UI says it was refused instead of showing a pending approval
- **AND** until then checking again raises no fresh approval for the same target; the changed target drops the old refusal and a fresh pending approval for it waits for a person

#### Scenario: an approval that cannot be applied stays pending
- **GIVEN** a pending replacement whose sealed value the current master key cannot open
- **WHEN** it is approved with a presence grant
- **THEN** the approval is not recorded as approved, it stays pending with its sealed value, and the old value is unchanged

#### Scenario: changing where a secret goes asks again
- **GIVEN** an MCP server whose secret is approved for its command line
- **WHEN** its command is changed to another program
- **THEN** the secret is withheld and a pending approval names the new command line
- **AND** after the approval is applied with a presence grant the server receives the secret again

#### Scenario: moving a provider connection's base URL asks again
- **GIVEN** a provider connection whose key the model proxy already receives
- **WHEN** its base URL is changed, and separately its key is replaced
- **THEN** the key is not handed to the proxy or the engine for the new URL until the approval naming that URL is applied, and the replaced key waits sealed until its own approval is applied
- **AND** once each is approved the proxy is refreshed with the key

#### Scenario: adopting an MCP entry never replaces or deletes a secret it did not create
- **GIVEN** a registered server citing a secret ref, and an agent's config entry whose adoption maps a secret key to that same ref
- **WHEN** the entry is adopted, and again under a name that is already taken
- **THEN** the first is refused with `ADOPT_SECRET_REF_EXISTS` (409), the second with the name-conflict error before any value is written, and the existing secret still holds its value and is still approved for the server citing it
- **AND** a ref that is a standalone `secret/<name>` is refused the same way

#### Scenario: a stored key goes only to the endpoint of the connection that holds it
- **GIVEN** an MCP server's token stored under a ref, and a saved provider connection whose key is another ref
- **WHEN** `POST /api/v1/models/list-models` or `/test-connection` is sent that ref with a base URL no saved connection holds it for, or a ref no connection holds
- **THEN** each is refused as a validation error before anything is decrypted or sent, whatever protocol the request names, while an inline typed key and a saved connection's own ref and base URL work as before

#### Scenario: a value supplied for its destination needs no approval
- **GIVEN** a secret stored under a ref nothing has ever received
- **WHEN** a destination citing that ref is registered
- **THEN** the binding is recorded as approved with the registration, and the secret is injected when the destination first uses it

### Requirement: Answer a pending approval on the command line by waiting or exiting
The command line is the one surface that saves a secret and then waits on a person: `coffer
secret set` MUST print `waiting for approval in the Coffer app` with what waits and its approval
id, and exit `9`, when the value it stores is held for approval (a new standalone secret, or a
replacement of a value a destination already receives); with `--wait` it MUST poll until the person
answers, exiting `0` once approved and non-zero once rejected. What a change waits on includes a
pending replacement of the value of a secret that a destination cites, not only a pending binding
to it. The command line neither lists nor answers approvals: they are listed on the Secrets page
and `GET /api/v1/secrets/approvals`, refused with the Reject button or `POST .../reject`, and
approved only in the desktop app, so no command approves.

#### Scenario: the command line reports a pending approval and exits 9
- **GIVEN** a secret already sent to one MCP server
- **WHEN** the user stores a new value for it with `coffer secret set`
- **THEN** the command prints "waiting for approval in the Coffer app" naming the approval, and exits `9`
- **AND** `GET /api/v1/secrets/approvals` lists that approval

#### Scenario: the command line waits for the approval with --wait
- **GIVEN** a `coffer secret set` run with `--wait` whose change waits for approval
- **WHEN** the approval is applied in the desktop app
- **THEN** the command reports it approved and exits `0`

#### Scenario: the command line reports a pending provider key and exits 9
- **GIVEN** a provider connection whose key is stored under a ref and in use
- **WHEN** the user stores a replacement value for that ref with `coffer secret set`
- **THEN** the command prints "waiting for approval in the Coffer app" naming its approval and exits `9`, while the stored key keeps its old value
- **AND** a `coffer secret set` of an identical value exits `0`

### Requirement: Turn the protection off only through the desktop app
`secrets.require_approval` (`GET|PUT /api/v1/settings/secret-boundary`) MUST
switch on at once and MUST switch off only through a pending
`disable_protection` approval applied with a presence grant; no environment
variable, config file or CLI flag switches it off.

#### Scenario: switching the protection off waits for the desktop app
- **GIVEN** the protection is on
- **WHEN** `PUT /api/v1/settings/secret-boundary` is sent turning it off
- **THEN** it answers a pending `disable_protection` approval and the protection stays on
- **AND** once the approval is applied with a presence grant a new destination is approved without asking

### Requirement: Move plaintext secret files into the store
`POST /api/v1/secrets/scan` MUST report every
plaintext secret in `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json`
(a flat map of strings) and in the skill master store (assignments whose name
says password, secret, token or key, and well-known token shapes) by file,
line, key and proposed name, every skill that still mentions
`~/.coffer/secrets/`, and how many files it read (`files_checked`); it MUST NOT
return a value. When a skill still mentions `~/.coffer/secrets/`, the scan MUST
also carry `handoff`, a prompt (Principle IV, AI-Native) that asks the person's
agent to rewrite each such command to get its value through
`coffer run --secret ENV=NAME -- …` or `coffer run --env-file` with
`coffer://secret/<name>` references, to show the person the diff, and never to
print, copy or read a value; the prompt names only each mention's skill, file,
line and the path it reads, and the secret name each key of a secrets file
becomes — never a value and never a file's contents. With no mention the scan
carries a `null` `handoff`. The Find plaintext keys dialog keeps listing the
mentions for the person to update by hand and offers Copy prompt and, where a
managed agent is available, Ask an agent beside them.
`POST /api/v1/secrets/import` (the dialog's Import button, taking the chosen
finding ids and an optional dry run) MUST store each chosen value as `secret/<proposed name>`,
confirm the store reads back the same value, and only then replace the value in
its file with the reference, atomically and keeping the file's mode; a name that
is new waits for approval like any new standalone secret (the finding is skipped
as waiting, the value is not stored and its file is untouched, and importing
again once the approval is applied moves it); a name already holding a different
value MUST be skipped with its file untouched; a
file that cannot be rewritten MUST leave its findings skipped as `stored` —
naming the secret the value is now stored as, the file still holding it — while
the other files are rewritten, and importing the same findings again MUST retry
the file; a dry run writes nothing. Each value stored MUST be audited as
`secret_imported` without the value.

#### Scenario: a scan names plaintext secrets without their values
- **GIVEN** a `~/.coffer/secrets/db.env` holding a password and a skill whose script assigns a token
- **WHEN** the scan runs
- **THEN** both are reported with their file, key and proposed name, and the response contains neither value

#### Scenario: a skill still reading a secrets file is handed to an agent
- **GIVEN** a `~/.coffer/secrets/db.env` holding a password and a skill whose script sources that file
- **WHEN** the scan runs
- **THEN** its hand-off names the skill, the script's path and line and the file it reads, the secret names the file's keys become and how `coffer run` hands a secret to one command, and asks for the diff
- **AND** the prompt contains no value from either file, the dialog's Copy prompt carries the same text, and nothing on disk has changed

#### Scenario: importing moves a value and leaves a reference
- **GIVEN** those findings
- **WHEN** they are imported
- **THEN** a dry run changed nothing, and the first import stores nothing and leaves every file as it was, with one pending `add_secret` approval per name
- **AND** once those approvals are applied with a presence grant, importing again makes each value read back from the store under its standalone name and each file cite `coffer://secret/<name>` in place of the value with its mode unchanged

#### Scenario: a file that cannot be rewritten keeps its key and says so
- **GIVEN** a plaintext secrets file in a folder Coffer cannot write
- **WHEN** its finding is imported, after the approval that new secret waits for was applied
- **THEN** nothing is reported moved, the finding is skipped as `stored` naming its secret and why, the file is unchanged, the store holds the value and one `secret_imported` entry names it
- **AND** importing the same finding again once the folder is writable moves it and rewrites the file

#### Scenario: a scan that finds nothing says how many files it read
- **GIVEN** a secrets folder whose only file holds no secret
- **WHEN** the scan runs
- **THEN** it reports no findings and at least one file read

### Requirement: Approve several bindings in one confirmation
A person MUST be able to approve several pending approvals under one presence
check, for the case that a change leaves a handful of destinations waiting at
once. `POST /api/v1/secrets/approvals/approve` takes a list of `{id,
fingerprint}` — each approval's id and the target fingerprint it was shown
with — and ONE presence grant for the operation `approve_batch`, whose target is
`batch:` followed by the SHA-256 of the sorted `id:fingerprint` lines of exactly
that list. The daemon MUST recompute the target from the list it receives, so
the set approved is the set the person was shown: a grant signed for another
list, for a single approval, or by anyone but the desktop app is refused with
`PRESENCE_GRANT_INVALID` and approves nothing, and a batch grant authorises no
single approval. The daemon MUST then apply each item only if it is still
pending, is not the switch that turns the protection off, and is still pinned to
the fingerprint listed; every other item is skipped, left as it is, and
reported with its reason (`changed`, `not_pending`, `not_found`,
`not_batchable`, `failed`). Nothing outside the list is touched, and nothing is
approved by any other path — no selection, default or "approve all" runs without
the grant. Turning the protection off MUST still be approved on its own.
`POST /api/v1/secrets/approvals/reject` refuses several at once and, like
refusing one, takes no presence. The command line has no approvals command:
approving is the desktop app's.

In the desktop app the shell, not the page, decides what is covered: it reads
each selected approval from the daemon, keeps those still waiting, names the
first few in its own operating-system prompt and counts the rest, and signs over
that list. The web UI MUST show the pending approvals as one table in a dialog: a row per
change with its kind, the secret, where it goes (what uses it, or the target
that receives it), who asked and when. Once two or more wait, a header checkbox
selects rows, nothing is selected to begin with, and the buttons read **Reject
all** and **Approve all N…** until rows are selected, then **Reject N** and
**Approve N…** beside "N of M selected". **Approve…** runs the shell's presence
check directly, over exactly the rows it covers; there is no second review step,
because the table already is the review. Afterwards the same rows say, per
change, approved or skipped and why. Rejecting shows a toast and keeps no list
of refused changes. In a browser Approve MUST be disabled, naming the desktop
app, while Reject stays available.

#### Scenario: one confirmation approves every binding shown
- **GIVEN** three pending approvals for three destinations that cite one secret
- **WHEN** one `approve_batch` grant signed over exactly those three is sent with the three `{id, fingerprint}` pairs
- **THEN** all three are approved, each destination receives the secret, and each approval is audited as approved

#### Scenario: a batch grant covers exactly the bindings shown
- **GIVEN** three pending approvals and a batch grant signed over two of them
- **WHEN** it is sent with all three, or a single-approval grant or a swapped fingerprint is sent instead, or the batch grant is used to approve one approval alone
- **THEN** each attempt is refused with `PRESENCE_GRANT_INVALID` and all three still wait

#### Scenario: a binding whose target changed is skipped
- **GIVEN** three pending approvals shown to a person, and one server whose command is changed before the confirmation
- **WHEN** the batch grant over the three is sent
- **THEN** the changed server's old approval is skipped as no longer pending and its new approval for the new command still waits, while the other two are approved

#### Scenario: a fingerprint that is not the one shown is skipped
- **GIVEN** a batch whose list names an approval with a fingerprint other than the one it is pinned to
- **WHEN** the grant over that list is sent
- **THEN** that item is skipped as `changed` and stays pending, and the others are approved

#### Scenario: nothing in a batch is approved without a present human
- **GIVEN** three pending approvals
- **WHEN** the batch is sent with no grant, with a forged signature, or with a grant already used
- **THEN** it is refused (`422` or `PRESENCE_GRANT_INVALID`) and nothing is approved

#### Scenario: approving several waits for a review of every change
- **GIVEN** three changes waiting, in the desktop app
- **WHEN** the person opens the approvals dialog
- **THEN** the table lists all three with their destinations and targets and none is ticked to begin with, and nothing is approved until **Approve…** runs the presence check over the rows it covers

## REMOVED Requirements

### Requirement: Confirm a command-line delete unless forced
**Reason**: `coffer secret rm` is removed from the command line; the Secrets page confirms a delete in a dialog.
**Migration**: Delete a secret on the Secrets page or with `DELETE /api/v1/secrets/{ref}`.

### Requirement: Check a secret's presence on the command line
**Reason**: `coffer secret get` is removed from the command line.
**Migration**: `coffer secret list` shows whether the store holds a ref, and the Secrets page shows presence without decrypting.
