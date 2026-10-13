# Knowledge Files Stay Where Their Writer Put Them

**Status**: Accepted
**Date**: 2026-10-13
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md); [Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](knowledge-stays-current-through-flags-coffer-computes.md); [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md); spec knowledge "Sweep the knowledge root on its mechanical duties", "Link pages by slug and check every link", "Check a collection mechanically on every read"; OpenSpec change `keep-knowledge-files-in-place-and-import-readable-sources`

## Context

A collection is a tree of Markdown files that people and agents write
together. Since `pages/` and `sources/` were introduced, the knowledge sweep
had a fifth duty: any Markdown file outside `pages/`, `sources/` and `assets/`
(other than the README) that had been quiet for a minute was moved into
`pages/` at the same relative path, suffixed `-2` on a collision. It was
written for collections made before the two folders existed.

In practice the files people keep at a collection's root are not misplaced
pages. A collection that describes itself without Coffer has an `index.md`
(every page, grouped), a `log.md` (an append-only maintenance log) and a
`schema.md` (the page and evidence rules), and links pages with ordinary
relative Markdown links. The sweep carried those three into `pages/` a minute
after they were written, and every relative link to or from them broke. The
`-2` suffix renamed a file whenever its name was taken, which breaks links the
same way.

The check had the matching blind spot: it only understood `[[slug]]`. A page
reached from the root `index.md` by a relative link to `pages/gateway.md` was an
orphan, a relative link to a file that does not exist was never reported, and
the root files themselves could not count as navigation.

The forces:

- **The files must stand on their own.** The person wants a collection that is
  readable, navigable and checkable with no Coffer at all: in an editor, in
  Obsidian, on a git host. That rules out any rule that only Coffer knows.
- **A move is never neutral.** Moving or renaming a file changes its identity
  (the path is the identity), breaks relative links in both directions and
  invalidates whatever outside the collection pointed at it.
- **Coffer does not judge content.** Deciding that a root file is a page is a
  judgement; the tidy hand-off exists so that an agent makes such judgements
  with the person watching, in one reviewable change.

### How comparable products handle it

- **Obsidian** never moves a note on its own. A note goes where the person
  creates it; links are updated only when the person renames or moves a file
  themselves, and both `[[wikilinks]]` and standard relative Markdown links are
  first-class.
- **Logseq** keeps pages in its `pages/` folder but does not relocate files a
  person put elsewhere; it reads the graph where it is.
- **Foam** and **Dendron** (VS Code) check both wiki links and Markdown links
  and report dead ones; neither reorganises the folder.
- **Static-site generators** (MkDocs, Docusaurus, VitePress) resolve relative
  `.md` links against the linking file and warn on a broken one; the source
  tree is the person's.

The common pattern: the tool **reads the tree as it is**, resolves standard
relative links, and **never moves files in the background**. Reorganising is
an explicit action whose link updates happen in the same step.

## Options Considered

### Option A — Keep filing, add exceptions for `index.md`, `log.md`, `schema.md`

- Pro: smallest change.
- Con: every new convention a person adopts (`glossary.md`, a `decisions/`
  folder) needs another exception, and the person's layout is wrong until
  Coffer learns it.
- Con: still renames on collision and still breaks relative links.
- Why it lost: it treats the symptom; the rule that files move is the problem.

### Option B — Never move files in the background; any file outside `pages/` and `sources/` is a collection file (chosen)

The sweep loses its filing duty and the quiet-minute retry. Every file keeps
its path. Markdown outside `pages/` and `sources/` (root management files, a
person's own folders) is a collection file: listed, read, committed and
restored like any other, never checked as a page, and its links count as
navigation. Standard relative links are resolved against the linking file
inside the knowledge root and checked like wiki links (`dead_link`, and
`outside_link` for a link that leaves the root).

- Pro: a collection's own files describe it completely; nothing about its
  layout is a Coffer secret.
- Pro: links survive, because nothing renames what they point at.
- Pro: a layout from before `pages/` existed stays valid; an agent moves pages
  during a tidy, where it can fix the links in the same change.
- Con: a page written at the root by an agent that ignored the guide stays
  there until a tidy moves it. The guide and the tidy prompt still say where
  pages go.

### Option C — Keep filing, but only when the person runs a migration

An explicit "migrate layout" command with a preview, link rewriting and undo.

- Pro: a one-click way to adopt `pages/` for an old collection.
- Con: a link-rewriting migration is a sizeable feature for a case the tidy
  already covers, with the agent rewriting links as it moves pages.
- Why it lost: not needed now; nothing in the collections asks for it. If it
  is ever added it must be explicit, previewed, never overwrite silently,
  never suffix names, and be undoable.

## Decision

**Option B.** No startup pass, sweep, file watch, reconcile or other background
entrance moves or renames a file in a collection. An upload or an explicit
import creates the files it names and nothing else; it never grants permission
to rearrange existing files.

Rules a future change must respect:

- **The path is the person's.** Only an explicit action by a person or an agent
  moves a file.
- **Collection files are first-class.** Anything outside `pages/` and
  `sources/` is read, listed, kept in history, carried by a delete and its
  Undo, and exported with the vault.
- **Both link forms are checked.** `[[slug]]` and standard relative Markdown
  links resolve, and a link that leaves the knowledge root is reported, never
  followed.

## Consequences

- The `-2` collision suffix is gone from the sweep; it remains only where an
  upload names a new source.
- Commits named `layout` stay in older history; nothing writes them now.
- The check reports `outside_link` as a new finding kind, and dead relative
  links appear where they were silently ignored before.
