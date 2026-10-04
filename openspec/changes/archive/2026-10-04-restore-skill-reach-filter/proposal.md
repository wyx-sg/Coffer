## Why

The Skills list lost its reach filter in the 0.2.0 rebuild. The only way left to
see which skills reach one agent was the link from that agent's Skills tab, and
the Requires tab cut long skill names short at 124px.

## What Changes

- The Skills list gets a **Reach** filter under its search: all skills, or only
  the skills that reach one chosen agent. It reads and writes the page's
  `?agent=` parameter, so the agent tab's link lands with that agent chosen.
- The Requires tab shows every name in full: each group's name column is as wide
  as its longest name, and the rows of a group still line up.

## Impact

- `frontend/src/components/skills/SkillLibrary.tsx`, new `SkillReachFilter.tsx`,
  `lib/agents/agentFilter.ts` (`useSetAgentFilter`).
- `frontend/src/components/skills/SkillRequiresTab.tsx`, `SkillRequireRow.tsx`,
  new `lib/skills/requireColumns.ts`.
- Specs: skill-manager, web-ui.

The two requirements are edited in `openspec/specs/` directly: the change renames
the scenario "the library has no reach filter and groups skills by what they
need", which a MODIFIED delta cannot express.
