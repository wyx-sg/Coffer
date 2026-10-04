## MODIFIED Requirements

### Requirement: Lead a transcript turn with the person's own words
**Readable means the person's words lead.** A "user turn" in a transcript is not only what the user typed: every harness prepends its own blocks to the same turn — reminders, task notifications, environment dumps. The conversation MUST read the turn as the person's, not the harness's: it MUST lead with their words, with the prepended blocks folded away rather than dropped — the blocks are part of the record and a view that discarded them would be claiming the turn said less than it did. A turn made only of harness blocks MUST still render, as what it is. Blocks are identified by SHAPE, not by a list of block names: naming them one at a time never finishes, and prose that merely contains a `<` is not markup. The person's turns MUST also be set apart from the agent's at a glance: the person's words sit in a right-aligned bubble, consistent with the Chat page, and the agent's replies stay unboxed on the other side under its mark; a turn made only of harness blocks is never put in the person's bubble.

#### Scenario: lead a turn with the person's words, not the harness's blocks
- **GIVEN** an opened conversation whose user turns include one led by a harness reminder block before the person's question, and one made only of harness blocks
- **WHEN** the conversation renders
- **THEN** the first turn leads with the person's question and the reminder block is folded behind it, not dropped
- **AND** the turn made only of harness blocks renders as harness text, with no empty bubble of the person's

#### Scenario: set the person's turns apart from the agent's
- **GIVEN** an opened conversation with a user turn, an assistant turn and a user turn made only of harness blocks
- **WHEN** the conversation renders
- **THEN** the person's words are in a right-aligned bubble and the agent's reply is unboxed under its name
- **AND** the harness-only turn is not in the person's bubble

### Requirement: List an agent's transcript sessions read-only
The system MUST expose a read-only listing of an agent's local transcript sessions, found at the location that type's child spec names. Each session summary carries its `session_id`, a derived `title` (the session's first *real* user turn, secret-scrubbed — a turn whose text is nothing but an injected markup block was written by the harness, not by a person, and is not a candidate, and neither is a turn that is nothing but attachment placeholders such as `[Image: source: …]`; placeholders inside an otherwise real turn are stripped from the title), `project_path`, `message_count`, `started_at`, `last_activity_at`, and the transcript file's absolute `source_path` — the last feeding the open / reveal affordances of "Open config files in an external editor or reveal them". The listing MUST support a case-insensitive substring search over title and project path, an exact `project` filter, sorting by `started_at`, `last_activity_at` (default) or `message_count` in either direction with `session_id` as the tie-break, and `limit`/`cursor` paging alongside the matched `total` ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"), because an agent accumulates thousands of sessions — and keeps writing new ones while a reader pages — and the surface cannot load them all. Parsing is per-file and cached by the file's modification time **and size**; a file that fails to parse is skipped rather than failing the listing. Message text is not carried on the wire by THIS listing and is not retained by it — a body travels only through "Read one transcript session in bounded windows", for the one session a reader opened.

Coffer never writes the transcript files, never stores their content and never sends them anywhere. It does not distil transcripts into memory: the agent's own memory is memory's domain, and [memory](../memory/spec.md) "Reintroduce no retired mechanism" forbids reintroducing a path that writes back into it.

#### Scenario: browse an agent's transcript history with title, search, and sort
- **GIVEN** a registered agent with several local transcript sessions across more than one project
- **WHEN** the agent's transcripts are listed with a search query, a project filter, and a sort key (`started_at`, `last_activity_at` or `message_count`)
- **THEN** each returned session summary carries a derived title, message count, `started_at`, `last_activity_at`, and the session file's absolute source path; only sessions whose title or project path matches the search and whose project matches the filter are returned, ordered by the requested sort key and direction, and paged by `limit` and the answer's `next_cursor` alongside the matched total — read-only, emitting no audit event and writing nothing

#### Scenario: a new transcript session does not shift the next page
- **GIVEN** an agent's transcript sessions read with `limit=2`, sorted by `last_activity_at`
- **WHEN** a new session is written and the next page is read with the first answer's `next_cursor`
- **THEN** the second page holds the sessions that followed the first page's last one, none of the first page's sessions and not the new one

#### Scenario: keep attachment markers out of a session's title
- **GIVEN** a session whose first turn holds only an image placeholder and whose next turn is an image placeholder followed by a question, and a session of image placeholders alone
- **WHEN** the transcripts are listed
- **THEN** the first session's title is the question with no placeholder in it, and the image-only session has no title
- **AND** a summary sidecar written before this rule is discarded and re-derived rather than served
