## MODIFIED Requirements

### Requirement: List an agent's transcript sessions read-only
The system MUST expose a read-only listing of an agent's local transcript sessions, found at the location that type's child spec names. Each session summary carries its `session_id`, a derived `title` (the session's first *real* user turn, secret-scrubbed — a turn whose text is nothing but an injected markup block was written by the harness, not by a person, and is not a candidate), `project_path`, `message_count`, `started_at`, `last_activity_at`, and the transcript file's absolute `source_path` — the last feeding the open / reveal affordances of "Open config files in an external editor or reveal them". The listing MUST support a case-insensitive substring search over title and project path, an exact `project` filter, sorting by `started_at`, `last_activity_at` (default) or `message_count` in either direction with `session_id` as the tie-break, and `limit`/`cursor` paging alongside the matched `total` ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"), because an agent accumulates thousands of sessions — and keeps writing new ones while a reader pages — and the surface cannot load them all. Parsing is per-file and cached by the file's modification time **and size**; a file that fails to parse is skipped rather than failing the listing. Message text is not carried on the wire by THIS listing and is not retained by it — a body travels only through "Read one transcript session in bounded windows", for the one session a reader opened.

Coffer never writes the transcript files, never stores their content and never sends them anywhere. It does not distil transcripts into memory: the agent's own memory is memory's domain, and [memory](../memory/spec.md) "Reintroduce no retired mechanism" forbids reintroducing a path that writes back into it.

#### Scenario: browse an agent's transcript history with title, search, and sort
- **GIVEN** a registered agent with several local transcript sessions across more than one project
- **WHEN** the agent's transcripts are listed with a search query, a project filter, and a sort key (`started_at`, `last_activity_at` or `message_count`)
- **THEN** each returned session summary carries a derived title, message count, `started_at`, `last_activity_at`, and the session file's absolute source path; only sessions whose title or project path matches the search and whose project matches the filter are returned, ordered by the requested sort key and direction, and paged by `limit` and the answer's `next_cursor` alongside the matched total — read-only, emitting no audit event and writing nothing

#### Scenario: a new transcript session does not shift the next page
- **GIVEN** an agent's transcript sessions read with `limit=2`, sorted by `last_activity_at`
- **WHEN** a new session is written and the next page is read with the first answer's `next_cursor`
- **THEN** the second page holds the sessions that followed the first page's last one, none of the first page's sessions and not the new one
