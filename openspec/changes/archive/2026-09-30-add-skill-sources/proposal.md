## Why

A skill could only come from a folder on this machine. Skills are shared as archives (`.zip`, and
Claude's `.skill`) and as folders in Git repositories, and a skill taken from a repository goes
stale: the only way to take its author's fixes was to find the folder again and re-import it by
hand. The Skills page also still carried the table, Overview tab and single-source dialog it had
before the skill detail was redesigned (Files · Delivery · Requires · History).

## What Changes

- **Archive import.** A `.zip` or `.skill` archive is uploaded (`POST /skills/stage/archive`, used
  by the web dialog and by `coffer skill add <file.zip>`) into a staging area. The whole archive is
  refused, naming the entries, for an absolute path, a `..` segment, a symlink or more than 50 MB
  once uncompressed (counted as it is read). A `SKILL.md` at the top or one folder down marks a
  skill; several are offered as a choice. Nothing is copied into `~/.coffer/skills/` until the
  user confirms, and the staging area is removed either way.
- **Git import.** A repository URL with an optional ref and subpath (a GitHub `tree/<ref>/<path>`
  address is read as all three) is cloned with this machine's `git` into staging, the ref resolved
  to one commit, and skills found by the same rule. The skill records a `git_import` source: URL,
  ref, subpath, pinned commit and the content hash of its folder at that commit. Git runs with no
  prompt and no credential from Coffer, so a public repository works and a private one works when
  the machine's own git already has a credential for it.
- **Staged folders.** The web dialog stages a folder the same way before adding it;
  `coffer skill add <folder>` still imports at once.
- **Upstream updates.** A Git-imported skill is checked on demand and every six hours (result kept
  on this machine in a new `skill_source_status` table). Update available shows the commit range;
  the preview lists added, removed and changed files with diffs and the commits; applying swaps the
  folder atomically, moves the pin and keeps reach and links, audited as an update. A folder edited
  since the pin makes the update a conflict with Keep mine, Take theirs and Compare. An
  unreachable source reports git's message and the last successful check. `coffer skill update
  <name>` is the command-line side.
- **Requirements.** `requires` in `SKILL.md` frontmatter is read into the skill's read model, so
  the Requires tab lists each command and links to its CLI page.
- **Skills page rebuild.** A library list (search, All / On / Off, multi-select bulk reach and
  delete, Built-in / Off / Copied / update marks) beside the open skill; detail tabs Files (SKILL.md
  rendered, Preview / Source, Edit) · Delivery (each agent's copy) · Requires · History (an empty
  state until the vault records skill versions); Check copies runs the existing drift report and
  repair; the Add skill dialog with Folder, Archive and Git repository; the Git source panel with
  update, preview, conflict and unreachable states.

## Capabilities

### New Capabilities

### Modified Capabilities
- `skill-manager`: archive and Git sources with staged confirmation; upstream updates for
  Git-imported skills; declared requirements in the read model; Check copies on the Skills page;
  the Skills page and skill detail layout.

## Impact

- Backend: `domain/skill/{source,discovery,content_hash,requires,git_url}.py`,
  `infrastructure/skill/{archive_reader,git_source,source_status_repo}.py`,
  `application/skill/{staging,source_ops,update_ops,update_worker}.py`,
  `surfaces/http/{skill_source_routes,skill_source_schemas,skill_source_wiring}.py`,
  `surfaces/cli/skill_source_cmd.py`; migration adding `skill_source_status`; new error codes
  `SKILL_STAGING_NOT_FOUND`, `SKILL_SOURCE_UNREACHABLE`, `SKILL_UPDATE_CONFLICT`,
  `SKILL_NOT_FROM_GIT`.
- Contract: skill-manager `api.openapi.yaml` regenerated (new routes, `SkillOut.requires`,
  `SkillOut.source_status`, the new source variants).
- Frontend: Skills page, skill detail, Add skill dialog and Git update dialogs rebuilt.
- Docs: the skills guide, the skill-manager architecture page and the security page's outbound
  list (a skill's Git source is an endpoint the user names, fetched by `git`).
- The `revise-web-ui-ia` change keeps only the agent Skills tab's unmanaged-skill requirements;
  the skill-manager requirements for sources and the Skills page move here.
