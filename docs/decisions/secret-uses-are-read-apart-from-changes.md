# Secret Uses Are Read Apart From Changes

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [Audit Every Change With Its Actor, Log Every Invocation, Prune Per Table](audit-and-retention.md),
[Only a Present Human Sees a Secret or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md),
[Standalone Secrets Are Named References Injected Into One Child](standalone-secrets-are-named-references-injected-into-one-child.md),
spec resource-framework "Tell a secret's use from a change in the audit log",
spec web-ui "Gather the three records on one Activity page",
architecture [observability](../../docs-site/architecture/observability.md)

## Context

The audit log records two different things in one table:

- **Changes.** Something in the vault became different: a server was added, a
  secret rotated, a setting switched. These are rare and each one matters.
- **Secret uses.** A secret's value left the vault and nothing changed:
  `secret_resolved` (Coffer handed the value to a server it started, or to a
  `coffer run` child) and `secret_revealed` (a person looked at it). Coffer
  writes one each time it starts a server that needs a secret, rate-limited to
  once a minute per secret, destination and slot.

The Activity page's Changes tab showed both. On a machine where a few servers
restart now and then, the uses outnumbered the changes many times over: the
screenshot that started this decision was a screen of identical rows, "Handed a
secret to a coffer run command", actor `coffer`, with the one change worth
reading somewhere below. Each row was also mislabelled (Coffer's own hand-off
to a server rendered with the `coffer run` sentence), but even correctly worded
rows bury the changes by their number.

The forces:

- **Every use stays recorded.** Who got a secret's value, and when, is the
  question an audit log exists to answer. Nothing may drop or merge rows in
  storage.
- **Changes must be findable at a glance.** The Changes tab is where a person
  goes to answer "what did I (or an agent) do to my setup?"
- **Paging and counts must stay honest.** The audit route pages with a cursor
  and returns `total`; a filter applied after paging leaves short or empty
  pages and wrong counts.
- **Old rows must read right.** The fix cannot depend on a migration of rows
  already written.

How comparable products separate the two (from their public docs; not
re-verified for this decision):

- **1Password Business** keeps the *Activity Log* (vault and item changes,
  member changes) apart from *Item Usage* reports (who viewed, copied or filled
  an item).
- **Doppler** has *Activity logs* for config and secret changes and separate
  *Access logs* for reads of secrets.
- **HashiCorp Vault** writes every request to the audit device; the UI's
  activity views count client use and do not mix it into a change history.
- **GitHub's audit log** keeps one stream but every row names actor, action,
  target and via, and its filters are by action category.

## Options

### A. A separate "Secret use" tab, read through a `nature` filter on the audit route (chosen)

The audit route takes `nature=change|use`; `use` means the event is one of the
secret-use events (`SECRET_USE_EVENTS` in `domain/audit.py`), `change` means it
is not. The filter is applied in the query, before paging and counting, and is
bound into the cursor. The Activity page gets a fifth tab, *Secret use*, that
reads `nature=use`; *Changes* reads `nature=change`; *Everything* reads both and
merges them as before. `coffer log audit --nature` reads the same split from the
command line. On the Secret use tab, repeated uses of one secret by one
destination less than ten minutes apart fold into one row with `×N`, display
only; the drawer lists every folded use.

- **Good:** Changes holds only changes again, with honest pages and counts.
  The uses are one click away and read as what they are, which is where 1Password
  and Doppler landed too. No schema change and no migration: the split is by
  event type, which every old row already has. The folding keeps the Secret use
  tab readable without touching storage.
- **Costs:** one more tab, one more query parameter and CLI option. The set of
  use events is a list the code has to keep current when an event is added.

### B. Keep uses in Changes behind a "hide secret uses" toggle

One tab, with a switch (on by default) that hides the use events.

- **Good:** no new tab; the uses stay next to the changes they relate to.
- **Lost because:** a hidden-by-default switch is a filter people forget is
  on, and the uses then seem to be missing. The tab would still be named
  Changes while showing uses when the switch is off. It needs the same
  server-side filter as A to keep pages honest, so it saves no work.

### C. Leave the uses in Changes and only fix the sentences

Rewrite each row to name its object and destination, change nothing else.

- **Good:** smallest change.
- **Lost because:** the sentences are part of this decision's fix, but by
  themselves they leave the volume problem: the changes stay buried under a
  page of correctly worded hand-offs. This was the user's complaint.

### D. Record uses in their own table (or split the event type)

Write uses to a new `secret_uses` table, or rename the events so the split is
structural.

- **Good:** the cleanest separation in storage; uses could get their own
  retention.
- **Lost because:** it needs a migration of existing rows (or leaves old rows
  on the wrong side), another table to sync, prune and export, and a second
  route for the same kind of record. The event type already says which side a
  row is on, so the query can split it without moving any data.

## Decision

Option A. The audit log stays one table; the audit route and `coffer log audit`
read changes and secret uses apart by event type through `nature`; the Activity
page shows them in two tabs, *Changes* and *Secret use*, and folds repeated uses
on display only.

## Consequences

- A new event in which a secret's value is used without changing anything must
  be added to `SECRET_USE_EVENTS`, or it lands in Changes.
- Retention is unchanged: uses and changes prune together under the audit
  table's policy.
- Folding is a view: export and the drawer still see every row.
