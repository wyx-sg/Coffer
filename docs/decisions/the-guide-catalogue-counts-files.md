# The Guide Catalogue Counts Files, It Does Not List Them

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md), [Knowledge Collections Own Their Format](knowledge-collections-own-their-format.md), spec knowledge "Merge the manual and the catalogue in the skill body"

## Context

The `coffer-guide` skill ends with a catalogue of the person's knowledge. A
collection that names a start page (`entry:` in its README) was listed by its
file count, since the start page is how it is read. A collection with no start
page had every Markdown file listed, grouped by folder, each with its path,
title and description. A 60,000-character budget shortened the whole
catalogue in two steps when it grew: first every description was dropped,
then every collection fell back to a count.

Measured on the maintainer's machine: the rendered `SKILL.md` was 48 KB, and
21 KB of it was the file list of one collection without a start page. That
body is loaded every time an agent opens the skill for any reason, including
to look up how a Coffer tool works. Most of the list was sources (raw uploads)
whose titles say little, and it grew with every upload.

The list was written when a corpus was assumed to stay in the hundreds of
files and when agents had been seen not to search. Both have changed: one
collection passed that size, and the guide now tells an agent to grep the
collection for the exact string when the start page does not lead it there.

## Options Considered

1. **List every file, with a budget (the behaviour found).** Pros: an agent
   sees every title without a tool call, and can match a paraphrase against
   titles and descriptions. Cons: the cost grows with the corpus and is paid
   on every open of the skill; the budget makes the catalogue change shape
   suddenly, for every collection at once, when one of them grows; three
   levels of detail to render, test and explain.
2. **Count files per top-level folder (chosen).** A collection without a
   start page gets its count broken down by top-level folder, and is told to
   search the folder. Pros: the catalogue is as long as the collections'
   layouts, not their contents, so it needs no budget and never changes
   shape; the counts still tell an agent where the bulk is (`pages/` 40,
   `sources/` 200); one code path. Cons: no titles in context, so finding a
   file costs a listing or a grep; a paraphrase that matches no file name and
   no text is found only by reading an index, which the collection has to
   keep.
3. **List titles only, never descriptions.** Pros: about half the size. Cons:
   still grows with the corpus, and still needs a budget.
4. **Have Coffer write an index file into each collection and point at it.**
   Pros: the list exists, outside the skill body. Cons: Coffer would write a
   file into a collection whose format is the collection's own, and a
   generated index beside a hand-kept one is two indexes.
5. **List only pages, not sources.** Pros: drops the least useful part. Cons:
   "page" and "source" are the `llm-wiki` template's words; Coffer gives no
   folder a meaning except the uploads folder.

Comparable tools point at a place and let the agent search. Claude Code and
Codex ship no file index of a repository: the agent globs and greps. Agent
Skills load a short description first and the files only on demand. The
LLM-wiki pattern keeps an `index.md` that the agent maintains as part of the
wiki, which is exactly what `entry:` names. Tools that inject a full listing
(repository maps) cap it by tokens and rank it, which needs the ranking
Coffer chose not to build.

## Decision

The catalogue lists no file by name. Every collection gets its description,
where its files live, its rules file and its start page when it names one.
Then one line: with a start page, its Markdown file count; without one, the
count for each top-level folder (and the root), and the instruction to search
the folder. The budget and the shortened forms are removed.

## Consequences

- The guide's body no longer grows with uploads. On the measured machine it
  drops by about 21 KB.
- A collection that wants its files discoverable by subject keeps a start
  page and names it with `entry:`. The `llm-wiki` template already does. A
  blank collection relies on file names and search.
- A file added by hand changes the guide only through a count.
- This replaces "a catalogue — every collection's documents with path, title
  and description" in
  [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md).
