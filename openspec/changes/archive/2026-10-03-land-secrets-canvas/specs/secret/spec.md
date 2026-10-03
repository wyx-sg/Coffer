## ADDED Requirements

### Requirement: List secrets with no value here and waiting approvals on Overview
The secret kind MUST contribute to the attention list ([resource-framework](../resource-framework/spec.md)
"Report what needs a person across every kind") one item for the **set** of
secrets that have no value on this Mac — cited by a resource but not stored
here, or stored under another Mac's master key and so unopenable (see "Show a
secret this Mac cannot open as missing on this Mac") — and one for the **set**
of approvals still pending. The first MUST read `secret_missing_here`, severity
`error`, with the reason "N secrets have no value on this Mac." ("1 secret has no
value on this Mac.") and the action `open` as a `GET` of `/api/v1/secrets`; the
second MUST read `secret_approvals_pending`, severity `warning`, with the reason
"N changes waiting for approval." and the action `review` as a `GET` of
`/api/v1/secrets/approvals?status=pending`. A `GET` action is a navigation: the
page it opens is the client's to choose. Each item's `uid` MUST be a short,
order-independent fingerprint of the set's members (the refs, the approval ids),
so its attention key identifies exactly that set: ignoring the item ignores that
set, and a secret going missing, a value being added, or an approval arriving or
being decided changes the key and brings the item back. Both count toward the
per-kind counts the sidebar badges and the menu bar read, and neither is listed
when its set is empty.

#### Scenario: secrets with no value on this Mac are listed on Overview
- **GIVEN** one secret cited by a resource but not stored here, and one stored under another Mac's key
- **WHEN** the attention list is read
- **THEN** it carries one `secret_missing_here` item, severity `error`, with the reason "2 secrets have no value on this Mac." and the action `open`, and the per-kind count for `secret` includes it
- **AND** with a pending approval it also carries one `secret_approvals_pending` item, severity `warning`, whose action is `review`

#### Scenario: an ignored secret item returns when the situation changes
- **GIVEN** the `secret_missing_here` item ignored by its key
- **WHEN** another secret goes missing
- **THEN** the item is listed again under a new key, and the earlier key still lists nothing

## MODIFIED Requirements

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

#### Scenario: a refused binding says it was refused and can be asked about again
- **GIVEN** a pending approval for a server's secret that a person rejects
- **WHEN** the server is next started or listed, and then its target changes
- **THEN** the first answers `SECRET_BINDING_REJECTED` (409, a refusal, not a wait) and a command that saved the server prints that it was refused and exits with the conflict code instead of `9`
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

### Requirement: Show a secret this Mac cannot open as missing on this Mac
`GET /api/v1/secrets` MUST mark a stored ref whose ciphertext this Mac's
master key cannot open as `locked`, found by checking each token's signature
against the key without decrypting any value and without an audit entry. The
Secrets page MUST show every row this Mac has no value for — cited but not
stored, or `locked` — as **Missing on this Mac**, with an **Add value** action
in place of its last use, and a banner counting them and naming the first of
them ("N secrets have no value on this Mac · linear, SeaTalk and sentry can’t
start until they have a value") whose **Add values** opens one dialog with a
field per missing secret, where a field left empty stays missing and **Save N
values** stores the rest. The banner offers no master-key import: importing a
key replaces this Mac's own, so it lives in the sync join flow and in Settings ›
Security. Adding a value MUST be an ordinary write of the ref, subject to the
same approvals as any other write, and reveal MUST be unavailable for such a
row. The same set is listed on Overview (see "List secrets with no value here
and waiting approvals on Overview"), and the banner's × ignores it exactly as
Ignore does there.

#### Scenario: a ciphertext from another Mac's key is listed as locked
- **GIVEN** a stored standalone secret encrypted with another Mac's master key, and one stored on this Mac
- **WHEN** the secrets are listed
- **THEN** the first is present and `locked`, the second is not `locked`
- **AND** no value is decrypted and no audit entry is written

#### Scenario: a value added for a locked secret replaces it once approved
- **GIVEN** a locked standalone secret
- **WHEN** a new value is posted for its ref
- **THEN** the answer is `202` naming a pending `replace_value` approval and the row stays `locked`
- **AND** once the approval is applied with a presence grant the row is no longer `locked` and the store reads back the new value

#### Scenario: a secret this Mac cannot open is missing on this Mac
- **GIVEN** a locked secret and a cited secret the store does not hold
- **WHEN** the user opens `/secrets`
- **THEN** both rows read "Missing on this Mac" with Add value, and a banner says 2 secrets have no value on this Mac and offers Add values, with no link to import a master key
- **AND** Reveal is unavailable for the locked row, and Add value posts the new value for its ref

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
refusing one, takes no presence. `coffer secret approvals` stays list-only:
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
