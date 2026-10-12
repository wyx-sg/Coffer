## Context

Every audit row already carries the fields that say what it touched
(`details`), but the page's sentences were written per event type with at most
the resource name. Secret uses are a different kind of record from changes and
far more frequent: Coffer audits each decrypt-for-use, at most once a minute per
secret, destination and slot.

## Decisions

- **Sentences are composed from `details` in the client.** No new columns and
  no backfill: old rows read the same as new ones. A missing field falls back to
  the sentence without it, never to a placeholder.
- **One event type, two sentences for `secret_resolved`.** A row with
  `destination_kind` is Coffer's own hand-off; a row with `argv0` is
  `coffer run`. Splitting the event type would leave every existing row on the
  old, wrong sentence.
- **Secret uses get their own tab** (user's choice, 2026-10-12, over a hide
  toggle on Changes or leaving them in place). See the ADR
  `secret-uses-are-read-apart-from-changes`.
- **The split is server-side** (`nature`), so a page of Changes is a full page
  of changes and its total is right; the use set is a domain constant beside
  `AuditEventType`.
- **Folding is client-side and display-only.** Rows of one secret and one
  destination (or program) less than ten minutes apart fold into the newest;
  the drawer lists each; the totals count rows.
