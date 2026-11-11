# Rules for this collection

This collection is a wiki that the developer and agents write together: pages
compiled from the sources kept beside them. These are its rules; follow them
whenever you read or write here. They were copied in from Coffer's LLM-wiki
template when the collection was created and are now this collection's own:
change them here to change how it is kept.

**Settings.** A page's check holds for **90 days**. Pages are written in the
language the collection is already written in.

## Layout

- `index.md` is the way in: every page by subject, one line each on the
  question it answers. Keep it current whenever you add, rename, merge or
  delete a page.
- `pages/` holds the **pages**: the wiki itself, compiled from the sources and
  kept up to date. This is what you read first and what you write.
- `sources/` holds the **sources**: material as it arrived (an upload, a file
  dropped into the inbox, an imported Confluence page), converted to Markdown.
  A source is the record of what arrived and is never edited, beyond the few
  keys rule 6 allows.
- An upload with pictures is a folder of its own in `sources/`: the source
  and its pictures side by side (`sources/deck/deck.md`,
  `sources/deck/image-1.png`). The source links them by bare name
  (`image-1.png`); a page that needs a picture links it by its path from the
  page (`../sources/deck/image-1.png` from `pages/`).
- Anything else (a folder of the developer's own) stays where it is.

## Answering from this collection

1. Start at `index.md`, then read the page that owns the subject in full. Take
   a page's conditions and limits together with its conclusion.
2. Go to a source only when the page does not say enough, through the page's
   `sources`. A source marked `superseded_by` or `ingest: skipped` is history,
   not an answer. Grep `sources/` only for a literal string (an identifier, an
   error message), and check what you find against the page that owns it.
3. A page whose `verified` date is older than the check interval may be out of
   date: say so when you rely on it, and check it against the code or system
   when the answer matters.
4. When you work out an answer the pages do not already give, write it back
   (see "Writing a page") and tell the developer in one line what you added.

## Page types

Every page under `pages/` has one `type` from this list. Change, add or remove
types here; agents follow this list.

- `overview`: where to start. What this collection covers and which pages to read first.
- `concept`: what something is and why it works the way it does.
- `entity`: one service, system or team. What it owns and how to reach it.
- `how-to`: the steps for one task.
- `decision`: a choice that was made, the options and the reason.

## Writing a page

Write down what is durable: how a service works, a convention this developer
follows, a decision and its reason, a trap and how to avoid it. Not a guess,
an opinion, or something true only of one conversation.

1. **Find its home.** Read `index.md` and grep `pages/` for the subject. If a
   page already answers the question this fact belongs to, read it in full and
   fold the fact into the section it belongs in. Only when no page owns the
   subject, create one under `pages/` at a slug of its title
   (`pages/session-ownership.md`), and add it to `index.md`.
2. **Lose nothing.** Integrate; never regenerate. Every fact already in a page
   you rewrite must survive your edit.
3. **One question per page, organised by subject, never by provenance.** Never
   add sections like "Added today" or "From the ticket". Another page that
   needs the fact links to its owner rather than repeating it.
4. **Where two statements disagree, the newer wins unless the older one is
   shown to be right** by a source, a date, a command's output or the code.
   Keep the superseded statement legible: "(previously recorded as X;
   corrected YYYY-MM-DD)".
5. **Say what is known and what is not.** Keep what a source or the code shows
   apart from what you infer, and name an open question as one rather than
   filling it in.
6. **Never edit a source.** The only keys you may add to one are
   `ingest: skipped`, `superseded_by: <slug>` when a newer source replaces it,
   and `summary`, one or two sentences on what it says.
7. **Link pages by `[[slug]]` or by a relative path.** A page's slug is its file
   name without `.md`. When you rename or move a page, update the links to it,
   or keep its old slug in its `aliases`.
8. **Give every page frontmatter**: `title`; `type` from the list above; a
   one-line `description` saying what question the page answers (it is what a
   reader chooses by); `sources`, the slugs of the sources it draws on; any
   `aliases`; and `verified: YYYY-MM-DD`, when you last checked it against its
   sources or the code. A page whose facts rest on code, configuration or an
   observation rather than a source names that in `evidence`
   (`code: <repo>/<path>`, `observed: <date>, <where>`). An `overview` needs
   neither. Never write a `verified` date for a check you did not make.

```markdown
---
title: Session ownership
type: concept
description: Which service owns a login session, and how long does it live?
sources: [auth-design-2024, oncall-notes]
aliases: [sessions]
verified: 2026-10-12
---
```

## Integrating sources

A source **waits** while no page lists it in `sources` and it is not marked
`ingest: skipped` or `superseded_by`. To integrate one:

1. Read the source in full.
2. Fold what it says into the pages that own its subjects, by the rules above.
   One source may touch many pages; that is the point.
3. Add the source's slug to the `sources` of every page you changed with it.
4. Give the source a `summary`.
5. When it replaces an older source (a newer version of the same document),
   add `superseded_by: <its slug>` to the older one and recheck every page that
   cites the older one. A superseded source stays: a page may still cite it for
   what used to be true.
6. When nothing in it is worth keeping (a duplicate, an empty export), add
   `ingest: skipped` instead.

## Tidying

When the developer asks you to tidy this collection, check it against these
rules first and fix what you find:

1. **Waiting sources**: integrate each, oldest first.
2. **Broken links**: Coffer reports them; fix each.
3. **Pages due a check**: `verified` missing or older than the check interval.
   Recheck each against its sources or the code, fix what changed and set
   `verified` to today. A page you cannot recheck keeps its date and goes into
   your report.
4. **Incomplete pages**: missing `title`, `type` or `description`, or with
   neither `sources` nor `evidence` (an `overview` excepted). A source cited by
   a page but superseded, with no newer one cited beside it.
5. **Structure**: merge pages that answer the same question, keeping every fact
   and source and the merged-away slug in `aliases`; split a page that answers
   several; give a subject mentioned across pages but owned by none its own
   page; make sure every page is in `index.md`.
6. Leave alone what you are not sure about (two pages that disagree with nothing
   to tell which is right, a deletion of much text, a change to these rules)
   and report it.
7. End your report with **Gaps**: questions the pages cannot answer and sources
   worth finding.

Change nothing that does not need changing. When the developer asks only for a
check, report what you would do and change nothing.
