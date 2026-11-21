# Handle features some agents lack

## Why

With six agent types, most features exist for only some of them, for three kinds of reason: the product offers no way (Cursor takes no custom model endpoint), its terms do not allow it (Antigravity's `agy` inside another tool), or Coffer has not built it yet. The backend already derives each type's `features` from its facets, but the web UI still named `claude_code` and `codex` in many files, so the scheduled-task picker offered Codex on a Mac without it. Several agents also read the same skills folders, so a skill's reach cannot keep it from all of them, and the reach panel did not say so.

## What Changes

- The scheduled-task agent picker lists only the agents the turn platform reports available here, and says so when none is.
- Agent types report the skills folders they read (`skill_dirs_read`); Cursor and OpenCode also read `~/.claude/skills`. The skill reach panel names the added agents that share a folder and the ones that also see a skill delivered for another.
- A lint gate, `scripts/check_frontend_agent_types.py`, keeps agent type names out of the web UI outside its agent modules and a listed set of files that hold per-agent values the daemon does not serve.
- The agents guide (English and Chinese) carries one support table, each gap marked "not offered", "terms" or "not yet"; a test keeps it equal to what the daemon reports.
- ADR what-coffer-does-for-an-agent-follows-from-its-facets and the research note multi-agent-feature-gaps.

## Impact

- Specs: agent-registry (report features, types), scheduled-tasks (task picker), skill-manager (new requirement "Name the agents that also see a skill").
- Code: `domain/agent/descriptor.py`, `surfaces/http/agent_routes.py`, contracts; the frontend's scheduled-task fields, reach controls, `lib/skills/sharedReaders.ts`; `scripts/`, `Makefile`.
- Docs: agents, skills and scheduled-tasks guides (English and Chinese), ADR, research note.
