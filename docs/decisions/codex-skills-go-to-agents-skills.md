# Codex Skills Go to `~/.agents/skills`

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec skill-manager "Deliver a skill as a directory link"; [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md); [Trim Skill Management to What an Agent Cannot Do](trim-skill-management-to-what-an-agent-cannot-do.md)

## Context

Coffer delivered a skill to Codex as a link under `$CODEX_HOME/skills` (`~/.codex/skills`). Codex's own source now marks that place as deprecated: `codex-rs/ext/skills/src/host_roots.rs` reads "Deprecated user skills location (`$CODEX_HOME/skills`), kept for backward compatibility", and the official "Build skills" docs name only `~/.agents/skills` as the user-level place. The vercel `skills` CLI installs Codex skills into `~/.agents/skills` too.

The old place still works today. If Codex drops the compatibility path, every skill Coffer delivered would vanish from Codex at once, and Coffer's copy check would still see every link in place and report nothing.

Claude Code does not read `~/.agents/skills`, so it is not affected.

## Options Considered

### Option A — Keep `$CODEX_HOME/skills`

- Pro: nothing moves.
- Con: it builds on a place Codex has deprecated; when it goes, Codex loses every skill silently.

### Option B — Deliver to `~/.agents/skills`, and move Coffer's old links there (chosen)

- Pro: the place Codex documents; matches other skill installers.
- Pro: the reconciler already owns its links, so moving one is a remove plus a create; a folder the person put in `~/.codex/skills` themselves is left alone and still listed as an unmanaged skill, because Codex still scans that place.
- Con: a one-time move on every Mac on upgrade.

### Option C — Deliver to both places

- Pro: works whichever place a Codex version reads.
- Con: Codex scans both, so every skill appears twice in its list and costs its description budget twice.

## Decision

Option B. The Codex adapter's skill home is `~/.agents/skills`. On reconcile, a link Coffer made under `$CODEX_HOME/skills` for a skill in the library is removed and recreated under `~/.agents/skills`. Discovery of unmanaged skills scans both places.

## Consequences

- Codex skills keep working when Codex removes the deprecated place.
- Other tools that read `~/.agents/skills` see Coffer's skills too; that is the point of the shared place.
- Docs and the architecture page name `~/.agents/skills` for Codex.
