## MODIFIED Requirements

### Requirement: Retain attachments on an adjustable policy
Attachment files MUST NOT accumulate without bound, and how long they are kept MUST be the
user's to choose. One retention policy named `attachments` covers the directory that holds
them — `~/.coffer/content/channel-media` (what a channel downloaded). It is listed by
`GET /api/v1/retention/policies` and set by `PATCH /api/v1/retention/policies/attachments`
like any table policy (a whole number of days, or `forever`; the change is audited), and
its default is 30 days, so a user who never chose keeps today's behaviour. The policy
is seeded at daemon start with the other policies and stored beside them. A file is past the
window when its mtime is older than the window; there is no size cap and no reference
check. On the retention cadence and on a full prune, files past the window are deleted
from that directory and the prune answers how many files it removed under `attachments`;
under `forever` nothing is deleted. A prune naming `attachments` sweeps only attachments.
`GET /api/v1/retention/policies/attachments/preview?days=<n>` counts the files held now and how many are older than `n` days and deletes nothing. A sweep that
fails is logged and skipped, never stopping the table prune.

#### Scenario: attachments are kept for thirty days unless the user chose otherwise
- **GIVEN** a fresh daemon and attachment files in the channel media directory, one of them 31 days old
- **WHEN** a full retention prune runs
- **THEN** `GET /api/v1/retention/policies` lists `attachments` at 30 days
- **AND** the 31-day-old file is deleted, the rest are kept, and the prune answers one file under `attachments`

#### Scenario: a changed attachments window decides what is deleted
- **GIVEN** a channel-downloaded file 10 days old and the `attachments` policy at 30 days
- **WHEN** a client sets the policy to 7 days
- **THEN** the preview for 7 days counts the file as one to delete before and nothing is deleted by the preview
- **AND** a prune naming `attachments` deletes the file

#### Scenario: attachments kept forever are never swept
- **GIVEN** the `attachments` policy set to `forever` and an attachment 400 days old
- **WHEN** a full retention prune runs
- **THEN** the file is kept and the prune answers no files removed under `attachments`

### Requirement: Page growing lists by an opaque cursor
A list that can grow while it is being read — the audit log, the MCP
invocation log, an agent's native sessions and the chat conversation
listing — MUST page by an opaque cursor rather than by `offset`. A request
MUST take `limit` and an optional `cursor`; the answer MUST carry
`next_cursor`, which is `null` exactly when no row follows the page. The list
MUST have a stable order with a unique tie-break, and the page read with a
cursor MUST hold the rows that follow the cursor's row in that order, so a row
written at the head between two reads neither repeats an earlier row nor
skips a later one. A cursor MUST be bound to the list and the filters it was
issued for: one that does not decode, or that is sent to another list or with
other filters, MUST be refused `400 CURSOR_INVALID`.

#### Scenario: a page read after new rows arrive neither repeats nor skips
- **GIVEN** an audit log of five entries read with `limit=2`, and a new entry recorded after the first page was read
- **WHEN** the next two pages are read with each answer's `next_cursor`
- **THEN** together the three pages hold the five original entries exactly once each, newest first, and the new entry is not among them

#### Scenario: the last page carries no next cursor
- **GIVEN** an audit log of three entries
- **WHEN** it is read with `limit=3`
- **THEN** the answer holds all three and its `next_cursor` is `null`

#### Scenario: a malformed or foreign cursor is refused
- **GIVEN** a cursor issued for the audit log filtered by one kind
- **WHEN** it is sent with another kind's filter, and a string that is not a cursor is sent as `cursor`
- **THEN** both requests are refused `400 CURSOR_INVALID`
