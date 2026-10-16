# File a Memory Where Its Agent Filed It

**Status**: Accepted
**Date**: 2026-10-16
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [Global Memories Live in a Claude Code Project of Their Own](global-memories-in-claude-code-live-in-a-global-project.md), spec memory "Keep every agent's memories in a hub in the vault"

## Context

The hub files each memory under a project or under `global`, and `global`
memories reach every Claude Code session through
`~/.claude/rules/coffer-memory.md`. The rule was: a memory typed `user` goes
to `global` whichever repository it came from.

On the owner's Mac, after a few days of syncing, `global` held 103 memories.
17 were Codex's profile of the person. 85 were the `User preferences` bullets
of individual Codex task groups ("the user chose command-local `--region` in
account-testkit", "create the Epic like SPB-66889"): preferences the person
stated while working on one project's task, which the reader typed `user`.
One was a Claude Code memory typed `user` in the solobase project. A Claude
Code session in an unrelated folder loaded account-project knowledge first.

A second cause: Codex's app runs each chat in a scratch directory
(`~/Documents/Codex/<date>/<chat>`) and writes the repository it worked on
beside it in `applies_to` (`cwd=<chat> (account implementation in
/Users/…/account)`). Only the first path was read, and the second kept a
trailing `)`, so these groups never resolved to their repository.

How comparable tools scope this: Claude Code keeps auto memory per project
and has no global memory at all; the person's own global rules live in
`~/.claude/CLAUDE.md`, which they write themselves. Codex files every learned
bullet under the task group whose `applies_to` names its working directory,
and keeps a separate profile in `memory_summary.md`. Windsurf separates
workspace memories from a short global rules file the person edits. None of
them promotes a memory to global by its type.

## Options Considered

### Option 1 — Keep "typed `user` goes to `global`"

- **Pros.** No change; a preference stated anywhere follows the person
  everywhere.
- **Cons.** Most of what Codex records as a preference is about one task in
  one repository. It loads into every session, crowds the 25 KB rules file
  and misleads sessions in other projects.

### Option 2 — Change it for Codex only

- **Pros.** Fixes the bulk (85 of 103).
- **Cons.** Two rules for one question. A Claude Code memory typed `user`
  inside a project stays global, though Claude Code itself filed it in that
  project.

### Option 3 — File a memory where its agent filed it (chosen)

A memory learned in a repository goes to that project, whatever its type.
One with no working directory (Codex's profile, a task group naming none)
goes to `global`. Every path in a Codex `applies_to` is read and the first
inside a repository wins. A memory learned only outside any repository goes
to `global` when typed `user` and is not published otherwise, as before.

- **Pros.** Coffer follows each agent's own scoping instead of overriding it
  with a guess from the type. `global` holds what is really about the person.
- **Cons.** A preference that is in fact general but was noted during one
  project's task stays in that project until the agent's own curation lifts
  it into its profile (Codex does this in `memory_summary.md`).

## Decision

Option 3, chosen by the owner on 2026-10-16. On the next sync the misfiled
memories move: their old `global` hub files are removed and they are
published under their projects.

## Consequences

- `global` shrinks to Codex's profile, preferences from task groups with no
  repository, and memories learned outside any repository.
- A Codex task group run from a scratch chat directory is filed under the
  repository its `applies_to` names.
- The type no longer decides scope; it is still carried in each memory's
  frontmatter.
