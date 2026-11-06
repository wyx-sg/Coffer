## Why

A review of skill management on 2026-11-06 found six defects in delivery and
import, and several features an agent does as well from a hand-off prompt. The
owner decided Coffer stays lean: what an agent can do, Coffer does not build.
The options are argued in ADRs `codex-skills-go-to-agents-skills`,
`accept-long-skill-descriptions-and-find-skills-below-a-repos-top` and
`trim-skill-management-to-what-an-agent-cannot-do`.

## What Changes

- Codex skills are delivered to `~/.agents/skills`; Coffer's old links under
  `$CODEX_HOME/skills` move there.
- A description over 1024 characters is accepted and stored shortened.
- Git and archive imports search down to 4 levels and list every skill found.
- A skill whose required skill misses one of its agents shows "Skill not shared"
  in Needs attention.
- The review prompt checks overlapping descriptions and suggests the native
  manual-only setting.
- Removed: change a Git skill's source; requirements from `profiles/*.md`; the
  per-agent delivery report; the unmanaged skill detail page; the orphan file
  viewer and delete; the compare link and merging any commit but the latest.
- Docs and CLI reference corrected to match.

## Impact

- skill-manager and web-ui specs (edited directly; scenarios removed and renamed).
- Skill application services, HTTP routes, CLI, contracts, frontend skill and
  agent pages; docs-site (English and Chinese).
