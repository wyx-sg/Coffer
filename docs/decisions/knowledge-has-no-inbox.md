# Knowledge Has No Inbox: an Upload Is Written Where It Stays

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Knowledge Collections Own Their Format](knowledge-collections-own-their-format.md), [Knowledge Files Stay Where Their Writer Put Them, and Every Link Is Checked](knowledge-files-stay-where-their-writer-put-them.md), spec knowledge "Store an upload the moment it arrives", "Hide every dot-prefixed entry"

## Context

Every collection had a hidden `.inbox/` folder with two jobs.

- **A staging step for uploads.** An upload was written into `.inbox/`,
  committed, then promoted into the uploads folder in the same call. The file
  never waited there; the step only existed because the inbox existed.
- **A second way for an agent to add knowledge.** A Markdown file dropped
  into `.inbox/` was adopted by the next sweep: frontmatter filled in, moved
  into the uploads folder, audited. This came from the time agents had a
  `coffer__write` tool and Coffer decided where a file went.

Since then collections own their format: an agent reads the collection's
rules file and writes the file where the rules say, with its own file tools,
and the sweep commits it as an edit on disk. The guide stopped telling agents
about the inbox. So the inbox was an entrance nothing pointed to, kept alive
by an intake module, a quiet-minute timer, an exception in the vault's ignore
list (the only hidden knowledge entry that was tracked), a row in every
filesystem table and a section in two guides. On the maintainer's machine both
inboxes were empty.

Coffer's rule is to do nothing the agent can do itself.

## Options Considered

1. **Keep the inbox as it is.** Pros: an agent with no idea of a collection's
   rules has one fixed place to drop a file; another tool can hand Coffer a
   file without knowing the layout. Cons: nothing tells an agent to use it;
   it is a second filing rule beside the collection's own ("the sweep moves
   your file to `sources/`") in a system whose other rule is that files stay
   where their writer put them; it is the only hidden entry the vault tracks,
   so the ignore rule, the path guard, the history feed and delete-undo each
   carry an inbox case.
2. **Remove it; an upload is written straight into the uploads folder, and an
   agent writes by the collection's rules (chosen).** Pros: one way in for
   each kind of writer; an upload is one write and one commit of one file; no
   hidden folder of Coffer's in a collection at all; less code than any
   alternative. Cons: a tool that only knows "drop it in the inbox" has to
   learn the uploads folder, or call `coffer knowledge upload`; a file an
   agent writes carries only the frontmatter the agent wrote, since nothing
   fills it in afterwards.
3. **Keep the inbox only as the upload's staging step.** Pros: the submitted
   text stays in history under its inbox path even after the source is
   edited. Cons: the source's own first commit already holds that text; the
   staging step exists only to feed itself.
4. **Replace it with an `inbox:` key in the README, so a collection may name
   its own drop folder.** Pros: fits "collections own their format". Cons: a
   collection that wants a drop folder can already make a visible one and say
   in its rules what to do with it; Coffer would be adopting files again.

Comparable tools mostly do not have this feature. Obsidian has no inbox; an
"Inbox" folder is a habit people set up themselves, as a normal visible
folder. The LLM-wiki pattern this layer follows keeps new material in a
visible `raw/` or `sources/` folder the agent reads, with no adoption step.
Claude Code and Codex write their own memory files directly where they
belong. The tools that do have an inbox (task managers, read-later apps) have
it because a person captures faster than they can file; here the writer is an
agent that can read the rules first.

## Decision

A collection has no `.inbox/`. An upload or an import is converted and written
once, straight into the collection's uploads folder. An agent adds knowledge
with its own file tools, where the collection's rules say, and the sweep
commits it as an edit on disk. The sweep adopts nothing and moves nothing.
`.inbox` is an ordinary hidden name: ignored by the vault, listed and read by
no surface.

## Consequences

- The intake module, the inbox module, the quiet-minute rerun and the ignore
  exception are deleted. The sweep has three duties: commit edits on disk,
  close idle tidies, re-render the guide.
- A file left in a `.inbox/` folder is no longer picked up. Nothing is
  migrated: move such a file into the collection by hand.
- Older history still holds the `.inbox/` paths an earlier build committed.
  The change feed and an undo leave hidden paths out, so they never show or
  restore one.
- This replaces the sentences about the inbox in
  [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md)
  and [Tidying Knowledge Is the Agent's Job](tidying-knowledge-is-the-agents-job.md).
