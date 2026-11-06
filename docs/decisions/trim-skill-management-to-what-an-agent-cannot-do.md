# Trim Skill Management to What an Agent Cannot Do

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec skill-manager; spec web-ui; [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md); [Codex Skills Go to `~/.agents/skills`](codex-skills-go-to-agents-skills.md)

## Context

A review of skill management (2026-11-06) asked, for every feature, whether Coffer must do it or whether the agent the person already uses can. The owner's rule: Coffer stays as lean as possible; what an agent can do with a hand-off prompt, Coffer does not build. Coffer keeps what only it can do: the library, reach, delivery, sync, the source pin and the checks that find drift.

Comparable tools draw the same line: Claude Code and Codex read skills from folders and leave editing to the person or an agent; the vercel `skills` CLI installs and updates links but has no file viewer, change-source flow or per-agent delivery report.

## Options Considered

### Option A — Keep every feature

- Con: each one is UI, API, CLI, spec and tests to keep in sync, for work an agent does as well from a prompt.

### Option B — Remove what an agent can do, keep what only Coffer can do (chosen)

Removed:

- **Change a Git skill's source** (dialog, routes, CLI `skill source change`/`change-apply`). Remove the skill and add it again from the new source.
- **Requirements read from `profiles/*.md`** and the merge rules for them. `profiles/` is not part of the AgentSkills standard; requirements are declared in SKILL.md only, and the review prompt asks the agent to move them there.
- **Per-agent delivery report** after a reach change. The copy check already reports a link that is missing or wrong.
- **Unmanaged skill detail page** and its file viewer. The row on the agent's Skills tab carries Adopt, Reveal in Finder and Delete; the Adopt and Delete dialogs list the files.
- **Orphan file viewer and delete.** An orphan folder is added to the library in place or revealed in Finder; the drift hand-off prompt has the agent move it aside if the person agrees.
- **"View upstream" compare link** and merging an arbitrary commit. The update banner shows the commit range; "I merged it" accepts only the latest commit the check found.

Added, because only Coffer knows the reach of each skill:

- A skill whose `requires_skills` entry is in the library but not delivered to the same agents shows "Skill not shared" in Needs attention.
- The review prompt asks the agent to compare descriptions with the skills beside it and to suggest the native manual-only setting where it fits.

### Option C — Hide the features behind a setting

- Con: the code and tests stay; nothing is saved.

## Decision

Option B. Features left out: refresh from the original folder, source change for local skills, usage stats, description budget display, a manual-only switch, one-click update, a replace preview file list. They stay out until a real need appears, and are then built at that time.

## Consequences

- Fewer routes, CLI commands and screens to keep in sync.
- Work that moved to an agent is reached through the existing hand-off prompts.
