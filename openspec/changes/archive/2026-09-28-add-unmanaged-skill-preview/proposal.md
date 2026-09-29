## Why

An unmanaged skill — a skill folder in an agent's own skill locations that Coffer does not manage — could only be opened in the OS file manager from its row on the agent's Skills tab. Deciding whether to adopt or delete one means reading its SKILL.md and files, and managed skills already have a detail page that shows exactly that.

## What Changes

- Clicking an unmanaged skill's row on the agent's Skills tab opens a detail page at `/agents/:uid/skills/unmanaged/:location/:name`: the name with Unmanaged and location badges, a back link to the agent's Skills tab, an Overview (SKILL.md description, path, location) and a Files tab (tree plus a read-only preview). An invalid folder opens too, with its reason shown first.
- The page header carries Open folder, Adopt (on success, on to the new managed skill's page) and Delete (on success, back to the agent's Skills tab). The Open folder button leaves the table rows; Adopt and Delete stay there.
- Three read-only routes: `GET /agents/{uid}/unmanaged-skills/{skill}?location=`, `.../files?location=` and `.../files/content?location=&path=`, with the managed viewer's containment, size cap and binary detection.
- `coffer skill files|cat` take `--agent` (and `--location`) to read an unmanaged folder.

## Capabilities

### New Capabilities

### Modified Capabilities
- `skill-manager`: adds "Preview an unmanaged skill read-only" and "Act on an unmanaged skill from its detail page".

## Impact

- Backend: `unmanaged_ops.get_unmanaged`, `SkillService.get_unmanaged`, three routes in `agent_unmanaged_skill_routes.py`, `coffer skill files|cat --agent`.
- Contract: `openspec/specs/skill-manager/contracts/api.openapi.yaml` (three operations, `UnmanagedSkillDetailOut`).
- Frontend: `UnmanagedSkillDetailPage`, `SkillFileBrowser` shared by both skill file trees, the unmanaged table's row navigation, en/zh strings.
- Docs: skills guide, CLI and REST references.
