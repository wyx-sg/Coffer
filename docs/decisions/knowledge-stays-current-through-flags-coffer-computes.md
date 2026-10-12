# Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md), [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md), [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md), spec knowledge "Check a collection mechanically on every read", "Mark a source superseded by the one that replaces it", "Ask for a recheck of a page after the collection's interval", "Start a collection's README with its rules written out", "Hand a tidy to the agent", OpenSpec change `keep-knowledge-current`

## Context

A collection is a wiki compiled from sources
([Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md)).
Pages say which sources they draw on (`sources:`) and when they were last
checked (`verified:`). Coffer computes mechanical findings on every read
(dead links, orphan pages, waiting sources and so on), shows them in **To do**,
and a tidy hands them to an agent.

Three things wear a wiki down, and the person asked for each to be handled
(我们的知识库有纠错，补充的功能吗？source 里的文件肯定是会过期的，另外我工作过程中也会积累新的知识):

1. **A source goes out of date.** A newer design doc or runbook replaces an
   older one. Pages compiled from the old one keep repeating it, and nothing
   says so.
2. **A page drifts from the world.** Its sources did not change, but the code
   or the system it describes did. `verified:` is written, but nothing reads
   it.
3. **What is learned at work never reaches the wiki.** An agent answers a
   question by reading sources or code, and the answer stays in that
   conversation.

The person also asked for the tidy to say what the wiki is missing and where
to look for it, as Karpathy's LLM Wiki lint does. Two smaller gaps came up on
the way: a new collection's README said nothing about the page types and rules
it is the schema for, so a person could not see what they were allowed to
change; and a source said what it was only through its title, so an agent
reading the catalogue had to open each one to know whether it mattered.

### How comparable products handle it

Research, as of 2026-10-12:

- **Karpathy's LLM Wiki** (the pattern this wiki follows). Ingest notes where
  new data contradicts old claims. A periodic lint looks for "stale claims
  that newer sources have superseded", orphan pages, concepts without a page,
  and suggests "new questions to investigate and new sources to look for".
  Good answers to queries "can be filed back into the wiki as new pages".
  Nothing structured links an old source to its replacement; the lint pass
  is expected to notice.
- **Guru**. Every card has a verifier and an interval (weekly, monthly,
  quarterly, yearly; community posts describe three months as the default).
  An unverified card stays visible and searchable, shows a trust mark, and
  lands in the verifier's queue. Answers from its AI can be turned into a
  draft card ("Draft a Card"), and unanswered questions are listed "to fill
  in knowledge gaps".
- **Notion** wikis. A page is verified until a date or indefinitely. On
  expiry the owner is notified and the page loses its check mark and its
  boost in search and Notion AI. It stays visible.
- **Slab** and **Document360**. A review interval per post or per project.
  Overdue posts get a banner or a "Stale" badge and a filter for editors.
  Nothing is hidden.
- **Confluence**. Archiving hides a page from the tree and quick search but
  keeps its links working. No native review timer; Marketplace apps fill the
  gap, and native expiry is still an open request.
- **Wikipedia** `{{Update}}` / `inaccurate=yes`. Tagging puts an article into
  a category that works as a queue. Tags are added by hand, and nothing links
  an article to the source that replaced it.
- **Obsidian** (OKF Reviewer plugin). Frontmatter `status: deprecated` and
  `stale_after:` dates with 30/90/180/365-day presets; overdue notes get a
  red dot.
- **Document360**, **ServiceNow**. "No results" search reports turn real
  demand into gap tasks.

The common pattern: stale content is **flagged, not hidden**; verification is
**a timer with a queue**, one to three months by default; **no product
propagates supersession** to the content that relied on it; answers are
written back either as drafts a person approves or by the agent and caught
by the next lint; gaps come from failed questions or from structure.

## Options Considered

### Decision 1 — marking a source out of date

**Option A — `superseded_by: <slug>` on the old source; Coffer flags the
pages that still lean on it (chosen).** The agent (or the person) adds one
key to the old source's frontmatter naming its replacement. It is one of the
few keys the guide lets anyone add to a source, beside `ingest: skipped` and
`summary` (Decision 6). Coffer then derives, on every read:

- a **`superseded_source`** finding on every page that cites the old source
  and no later source in its chain of replacements (v1 → v2 → v3: a page
  citing v1 and v3 is current, one citing only v1 is flagged). The finding
  names the newest replacement, the page goes into **To do**, and the next
  tidy rechecks it against the new source;
- the old source is no longer **waiting**, even when no page cites it;
- a `superseded_by` that names no source is a **`missing_source`** finding
  on the old source;
- the catalogue lists the old source as "superseded by …", so an agent
  reading the wiki knows it is no longer evidence.

- Pro: it does what no product we found does, carrying an outdated source
  through to the pages that depend on it. It is computed from the files, so
  it cannot drift, and it costs one frontmatter line.
- Pro: the old source stays, so a page can still cite it for history ("until
  2026-09 the timeout was 5s").
- Con: someone has to add the line. The guide asks the agent to add it when
  it integrates a source that replaces another, so in practice this happens
  in a tidy.

**Option B — delete or archive the old source.** Simple, but it destroys
the record, and every page citing it becomes a `missing_source` finding with
no hint of what replaced it.

**Option C — leave it to the agent's lint, as LLM Wiki does.** Nothing to
build, but it depends on an agent reading every page against every source on
every tidy. The research shows this is exactly where wikis go stale.

### Decision 2 — rechecking pages on a timer

**Option A — a `stale_page` finding when `verified:` is older than the
collection's interval or missing; default 90 days (chosen).**

- The interval is 90 days unless the collection's README frontmatter sets
  `verify_after_days: <n>`. `0` turns the check off for that collection.
  This keeps the knowledge base as flexible as the person wants: a runbook
  collection can ask for 30 days, an archive for none.
- A page with no `verified:` is stale. The person chose this when PR3 was
  agreed (没写的也进待处理).
- A tidy rechecks stale pages against their sources or the code and writes
  `verified: <today>`. A page it cannot recheck keeps its date and goes into
  the report.
- Stale pages are flagged, never hidden, the same as in every product above.
  They stay in the catalogue and agents still read them.

- Pro: it uses a field the guide already asks for. One date comparison per
  page per read.
- Con: the first time it runs, every page without `verified:` is flagged at
  once (the person's own collections have about 60 pages). The first tidy
  after the upgrade clears them, and that is the point.

**Option B — fall back to the page's last change date when `verified:` is
missing.** Gentler on the first run, but the last change comes from git
history, which is one `git log` per page per read, and a file's mtime is
reset by sync on another Mac. An edit is also not a recheck.

**Option C — a per-page owner and a notification, as Guru and Notion do.**
Coffer has one person and their agents. An owner field would always name the
same person, and notifications have nowhere to go but **To do**, which is
already where findings go.

### Decision 3 — writing what is learned back into the wiki

**Option A — the agent writes it into the owning page as it works (chosen).**
The guide gains a rule: when you answer a question by reading a source, the
code or a system, and the answer is not already in the pages, write it into
the page that owns the subject (or a new page), add what you read to
`sources:` where it is a source, set `verified:` to today, and tell the
developer what you added. A guess, an opinion, or something true only of
this conversation is not written back.

- Pro: it is Karpathy's "file good answers back into the wiki", and pages
  are already the agent's to write. Every write is in the collection's
  history and can be undone.
- Con: a wrong answer can be written in. The next tidy and the `verified:`
  timer are the check, the same as in LLM Wiki.

**Option B — a draft the person approves, as Guru's "Draft a Card" does.**
Safer, but it adds a review queue the person would have to work through. We
rejected a review queue when the wiki was designed, and history plus undo
already covers a bad write.

### Decision 4 — reporting gaps and sources to look for

**Option A — a "Gaps" part of the tidy's report (chosen).** The tidy report
gains a section listing questions the pages cannot answer, subjects mentioned
across pages but owned by none (when the tidy did not create the page), and
sources worth finding (a spec, a runbook, a person to ask). The report is
already shown with the tidy in the change log.

- Pro: no new storage or UI. It is what LLM Wiki's lint suggests, and the
  agent is the one that can judge it.
- Con: it is prose in a change log entry, not a list Coffer can count.

**Option B — structured gap findings Coffer stores and lists in To do.**
Gaps are judgement, not mechanics. Coffer cannot recompute them from the
files, so they would be a second kind of state that goes stale.

**Option C — gaps from failed questions, as Document360 and ServiceNow do.**
Coffer does not see agents' questions or searches. Agents read the files
themselves, so there is no search log to mine.

### Decision 5 — what a new collection's README starts with

**Option A — write the defaults out: `verify_after_days: 90` in its
frontmatter, the description, then "## Page types" and "## Rules" (chosen).**
Creating a collection writes the README with the five default page types
(`overview`, `concept`, `entity`, `how-to`, `decision`), each with one line on
what it holds, and the rules every page follows (one subject per page, links
by `[[slug]]`, `sources` and `verified` on every page, what
`verify_after_days` does). The description stays the first paragraph, and only
the part **before the first `##` section** counts as the description, so
editing the description rewrites that paragraph and keeps the rules; a README
with no description has none, rather than its first rule.

- Pro: the README is the schema the guide already says wins over its
  defaults, and now the person can see the defaults and change them in the
  one file they already edit. The interval is visible where it is set.
- Con: an older collection's README has none of this; its defaults still
  apply, they just are not written down. A README a person wrote without
  sections keeps reading its first paragraph as before.

**Option B — keep the README to a heading and the description; the defaults
live only in the guide.** Smallest file, but the person cannot see what rules
their agents follow or where to change them, and `verify_after_days` would be
a key nobody knows exists.

**Option C — a separate `SCHEMA.md` or settings file.** It keeps the
description file short, but splits the schema from the file the guide and the
spec already call the schema, and adds a second file to keep out of the
corpus.

### Decision 6 — saying what a source holds

**Option A — a `summary` key on the source, one or two sentences the agent
writes when it integrates or tidies (chosen).** The catalogue shows it after
each source, and the Knowledge page shows it under each source in Contents,
next to the source's state (waiting, used by N pages, skipped, superseded).

- Pro: an agent reading the catalogue can tell which sources matter without
  opening them, and a person sees the same on the page. It is one more key on
  a file Coffer already reads on every listing, so nothing is stored.
- Con: it is written by an agent and can be wrong or missing. A tidy is told
  to give every source without one a summary, so the gap closes over time.

**Option B — Coffer fills it from the source's opening prose, as it does a
source's `description`.** No agent work, but the opening of a converted PDF is
usually a title page or a table of contents; the description already does
this and is often useless for exactly that reason.

**Option C — no summary; the title and the description are enough.** Nothing
to write, but the catalogue then lists sources by file name and title only,
which is what made agents open each one.

## Decision

1. Sources may carry `superseded_by: <slug>`. Coffer flags every page that
   cites a superseded source and no later source in its chain of
   replacements (`superseded_source`, naming the newest replacement), stops
   counting the old source as waiting, reports a replacement that names
   nothing as `missing_source`, and marks the old source in the catalogue.
2. Pages whose `verified:` is missing, unreadable or older than the
   collection's interval are `stale_page` findings. The interval is 90 days by
   default, and the README frontmatter's `verify_after_days` changes it (`0`
   turns it off; a value that is not a whole number of days, or is negative,
   keeps 90). A tidy rechecks stale pages and sets `verified:` to today.
3. The guide tells agents to write what they work out from sources, code or
   systems back into the owning page, never a guess, with `sources` and
   `verified` set, and to tell the developer what they added.
4. The tidy report ends with a Gaps section: unanswered questions, subjects
   without a page, and sources to look for.
5. A new collection's README starts with `verify_after_days: 90`, its
   description, and its page types and rules written out. The description is
   the first paragraph before the first `##` section.
6. Sources may carry a `summary`, written by the agent. The catalogue and the
   Knowledge page show it with each source's state.

## Consequences

- **To do** shows two new kinds: "Pages citing an outdated source" (naming the
  source and its newest replacement) and "Pages to recheck" (with the last
  check date, or "never checked"). Both go into the tidy prompt like every
  other finding. An open page due a recheck says **Needs rechecking**; an open
  superseded source says what supersedes it, as a link.
- At full detail the catalogue lists every source, each marked "(waiting)" or
  "(superseded by …)" and followed by its summary. Once it is shortened it
  lists only the waiting sources, as before.
- The first read after the upgrade flags every page without `verified:`. The
  guide tells the next tidy to recheck them, and that is the point.
- The coffer-guide's tidy steps gain "recheck stale pages", "give every source
  a summary" and "end the report with Gaps", its sources section gains
  `superseded_by` and `summary`, and its writing section gains writing answers
  back.
- Nothing is hidden or deleted automatically. Coffer flags, and the agent or
  the person decides.
- No search index is added. The catalogue stays in the coffer-guide skill
  until a collection outgrows its budget, which is when an index would be
  reconsidered ([Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md)).
- Linked folders are unaffected: Coffer computes no findings for them
  ([A Linked Knowledge Folder Is Shared in Place, Read-Only to Coffer, and Recorded Machine-Local](linked-knowledge-folders-are-read-only-and-machine-local.md)).
- Enforcement: spec knowledge "Mark a source superseded by the one that
  replaces it", "Ask for a recheck of a page after the collection's interval",
  "Start a collection's README with its rules written out", "Check a
  collection mechanically on every read", "Teach writing and tidying in the
  guide"; `infrastructure/knowledge/wiki.py` computes both findings.
