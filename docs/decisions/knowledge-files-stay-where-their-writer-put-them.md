# Knowledge Files Stay Where Their Writer Put Them, and Every Link Is Checked

**Status**: Accepted
**Date**: 2026-10-13
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md); [Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](knowledge-stays-current-through-flags-coffer-computes.md); [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md); [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [Confluence Pages Import as Readable Sources With Their Attachments](confluence-pages-import-as-readable-sources.md); spec knowledge "Sweep the knowledge root on its mechanical duties", "Link pages by slug or relative path and check every link", "Check a collection mechanically on every read"; OpenSpec change `respect-knowledge-file-locations-and-import-confluence`

## Context

A collection is a wiki: pages under `pages/`, sources under `sources/`, the
README with its rules at the root. Until now the sweep also *filed* loose
files. A Markdown file it found at a collection's root, or anywhere outside
`pages/` and `sources/`, was moved into `pages/` and a `daemon` change was
recorded. This was meant to keep the tree tidy without an agent.

In a real collection that a person and an agent had built by hand, it did
harm:

- **Navigation files were moved out of sight.** An `index.md`, a `log.md` or a
  `glossary.md` that the person kept beside the README was filed into `pages/`
  as if it were a page, then flagged as an unsourced page.
- **Links broke silently.** Agents link with relative Markdown paths
  (a link to `../pages/gateway.md`) as often as with `[[slug]]`. Moving a file
  broke every relative link to it, and the checker only read `[[slug]]`, so
  nothing reported the break.
- **Evidence was forced into the wrong shape.** A page backed by a ticket, a
  dashboard or a person's statement had to cite a source file or count as
  unsourced. Agents then wrote fake sources or set `verified` to dates nobody
  had checked.
- **One interval did not fit every page.** An on-call rota goes stale in weeks
  and an architecture overview in a year, but the collection had one review
  interval.
- **Page types were closed.** A `runbook`, `faq` or `incident` page was a
  finding until it was renamed.

The forces: a person's or an agent's chosen layout must survive; Coffer still
has to say what is broken; nothing should invite a fake answer.

## How comparable products handle it

- **Obsidian** never moves a note on its own. It links by `[[wikilink]]` or by
  a relative Markdown link, and when *the user* moves a note it rewrites the
  links to it. A broken link shows as a faded link; there is no auto-filing.
- **Logseq** and **Foam** likewise leave files where they are. Foam reports
  unresolved links as diagnostics and keeps a "placeholder" list rather than
  moving anything.
- **MkDocs** checks relative links at build time
  (`validation.links.not_found: warn`), and **Docusaurus** fails or warns on a
  broken Markdown link (`onBrokenMarkdownLinks`). Neither files documents; both
  check every relative link, including ones that leave the docs root.
- **Karpathy's LLM-wiki** pattern keeps an `index.md` and a `log.md` at the
  root as the wiki's own navigation, maintained by the agent, never treated as
  pages.
- **Wikipedia's** verifiability policy asks for a citation to any reliable
  source, not only an uploaded one, and an article's review cadence varies by
  topic rather than being global.

The common pattern: **the tool checks links and reports, the writer decides
where files live**, and evidence is whatever the reader can follow.

## Options Considered

### Option A — Keep auto-filing, but skip known names (`index.md`, `log.md`)

- Pro: the tree stays in the `pages/`/`sources/` shape without an agent.
- Con: every collection invents its own navigation names; the list is never
  complete, and each miss moves a file and breaks links.
- Con: relative links still break on every move.
- Why it lost: it keeps the harm and adds a list to maintain.

### Option B — Auto-file and rewrite links after the move

- Pro: tidy tree, and links survive.
- Con: Coffer would rewrite the person's text unasked, in a commit the person
  did not make, and a move into `pages/` still turns a navigation file into a
  page that is flagged.
- Why it lost: it changes what the writer wrote to fix a problem Coffer made.

### Option C — Never move; check every link; widen what counts as evidence (chosen)

- The sweep moves nothing. It adds frontmatter to a file dropped without it,
  adopts a dropped upload, and records a change; that is all.
- A file at the collection root other than the README (an index, a log, a
  glossary) is the collection's own file: listed as a plain file, never asked
  for sources and never counted as a page.
- Links are `[[slug]]` or a relative Markdown path. The check resolves both,
  relative to the file that holds them, reports a dead one as `dead_link` and
  one that climbs out of the knowledge root as `outside_link`.
- A page names its evidence in `evidence:` (URLs, tickets, people, sources);
  `sources:` remains for kept sources. A page with either is sourced. The
  README's `types_without_sources` names the page types that need neither,
  `[overview]` by default.
- `verified: null` is "not yet checked", never a date. A page may set
  `verify_after_days`; it overrides the README's `verify_after_days`.
- Any page type is accepted. The README lists the suggested ones; an unknown
  type is shown, not flagged.

- Pro: what the writer laid out stays laid out; nothing breaks behind them.
- Pro: every link is checked, including the relative ones agents write.
- Pro: honest evidence has somewhere to go, so fake sources and fake dates are
  never the cheapest way to clear a flag.
- Con: Coffer no longer guarantees the `pages/`/`sources/` shape. A collection
  can drift; the check reports dead and outside links, but not "a page in the
  wrong folder", because there is no wrong folder.
- Con: `evidence:` is free text. Coffer checks that it is present, not that it
  is true.

## Decision

**Option C.** Files stay where their writer put them. The sweep records and
adds frontmatter but moves nothing. Every link, `[[slug]]` or relative path,
is resolved and checked; a dead one is `dead_link`, one that climbs out
of the knowledge root `outside_link`. Pages cite kept sources or name other evidence; the
README names the types that need none and the default interval, and a page may
set its own.

Rules a future change must respect:

- **Coffer never moves a knowledge file on its own.** A move happens only when
  a writer (person, agent, restore) makes it.
- **Root files are the collection's.** The README and any file beside it are
  never pages or sources, and a restore brings them back byte for byte.
- **Unchecked is null.** No writer, Coffer included, puts a date in `verified`
  that nobody checked.
- **A link is checked where it is written.** Relative links resolve against
  the file that holds them, not the collection root.

## Consequences

- Collections laid out by hand keep their navigation files and their links.
- The `daemon` writer no longer files anything. Changes it recorded before
  this decision stay in history, described as an earlier version's filing.
- A collection that relied on auto-filing keeps the files where they now are;
  nothing moves back.
- The tidy hand-off gains `outside_link` findings; an agent fixes them by
  pointing the link at a file inside the knowledge root or turning it into a
  web link.
