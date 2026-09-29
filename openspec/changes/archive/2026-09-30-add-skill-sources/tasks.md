## 1. Domain

- [x] 1.1 `SkillSource` gains `archive_import` (archive name, folder) and `git_import` (url, ref, subpath, commit, content hash)
- [x] 1.2 Discovery rule (`SKILL.md` at the top or one folder down), content hash, lenient `requires` parsing, GitHub tree-URL parsing

## 2. Infrastructure

- [x] 2.1 Archive reader: refuse absolute / `..` / symlink entries and over-cap sizes before extracting, count real bytes while extracting
- [x] 2.2 Git source: clone into staging with the machine's git (no prompt, allowed transports, no submodules), resolve a ref, check out one subpath, list commits and changed files
- [x] 2.3 `skill_source_status` table, repo and migration

## 3. Application

- [x] 3.1 Staging registry (stage folder / archive / git, confirm with choice and replace, cancel, hourly sweep)
- [x] 3.2 Update check, preview (diff, local changes, conflict), compare, apply (atomic, pin moves, audited), keep mine
- [x] 3.3 Six-hourly update worker

## 4. Surfaces

- [x] 4.1 REST: stage routes, confirm, cancel, source check / preview / compare / apply / keep; `SkillOut.requires` and `SkillOut.source_status`; error codes
- [x] 4.2 CLI: `coffer skill add` for archives and Git URLs (`--ref`, `--path`, `--skill`, `--all`, `--yes`, `--force`); `coffer skill update`
- [x] 4.3 `make contracts`

## 5. Web UI

- [x] 5.1 Skills page: library list beside the open skill, search, All / On / Off, marks, multi-select bulk reach / delete, empty state linking to Agents
- [x] 5.2 Skill detail: Files (SKILL.md rendered, Preview / Source, Edit) · Delivery · Requires · History; old addresses redirect
- [x] 5.3 Add skill dialog: Folder, Archive, Git repository; found-skills step with choice, reasons and Replace; staging removed on close
- [x] 5.4 Git source panel: Check for updates, Update available, preview, conflict (Keep mine / Take theirs / Compare), unreachable
- [x] 5.5 Check copies: drift findings and Repair

## 6. Tests and docs

- [x] 6.1 Unit and integration tests: archive safety, discovery, git pin / update / conflict / unreachable over local bare repositories, CLI
- [x] 6.2 Vitest for the page, detail tabs, dialog and update states; e2e for the Skills page; visual baseline
- [x] 6.3 docs-site skills guide, skill-manager architecture page, security outbound list, CLI reference
