# Accept Long Skill Descriptions, and Find Skills Below a Repository's Top

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec skill-manager "Add skills from a Git repository", "Add skills from an archive", "Validate imported skill folders against AgentSkills"; [A Git Skill's Folder Is Fetched in One Request From a Partial Clone](git-source-partial-clone-prefetch.md)

## Context

Two import defects showed up when adding the public skill repositories on a clean machine:

1. A `description` over 1024 characters was refused. Anthropic's own `claude-api` skill in `anthropics/skills` could not be added. Neither agent refuses it: Codex's parser checks only the name's length (`codex-rs/skills/src/parser.rs`), and Claude Code only shortens the description in its list (1536 characters).
2. Adding from Git looked only one level below the chosen folder. At the top of `anthropics/skills` it found `template-skill` and missed the 19 skills under `skills/<name>/`; `openai/skills` keeps its skills under `skills/.curated/<name>/` and reported "no SKILL.md". Codex itself searches recursively.

## Options Considered

### Long descriptions

#### Option A — Keep refusing over 1024

- Con: Coffer refuses a skill both agents load.

#### Option B — Accept it; the stored record keeps the first 1024 characters with "…" (chosen)

- Pro: the skill's own SKILL.md is untouched, so each agent reads the full text the way it would without Coffer.
- Pro: the library record and API stay bounded.

#### Option C — Accept it and store it whole

- Con: an unbounded field in every list response, for text no Coffer screen shows in full.

### Finding skills

#### Option A — Keep one level

- Con: the common public repositories cannot be added from their top.

#### Option B — Search down to 4 levels, list every skill found, let the person pick (chosen)

- Pro: works for both public layouts; the pick list is the one archives already use.
- Pro: the depth limit keeps a huge repository from being walked whole.

#### Option C — Unlimited recursion

- Con: a large monorepo would be walked whole for a few skills.

## Decision

Option B in both. A description over 1024 characters is accepted and stored shortened with "…". Adding from a Git folder or an archive searches down to 4 levels below the chosen folder and lists every `SKILL.md` it finds.

## Consequences

- `anthropics/skills` and `openai/skills` add from their top.
- A skill four or more levels further down needs its folder named directly.
