# Tasks

## 1. Backend
- [ ] 1.1 `domain/skill/requirements.py`: parse `requires:` leniently, with warnings; `domain/versions.py` (version parse and compare, moved from agent detection)
- [ ] 1.2 `UserPath` moved to `infrastructure/platform/user_path.py`; `infrastructure/skill/command_probe.py` (locate, `--version`, login check with output discarded) and the Homebrew installer
- [ ] 1.3 `CliRequirementService`: aggregation per command, status, cache, check again, install jobs with streamed output and audit
- [ ] 1.4 Attention source `cli` composed in `attention_wiring.py`
- [ ] 1.5 REST `/api/v1/clis…` with Pydantic models; `OWNERS` entry; `make contracts`
- [ ] 1.6 CLI `coffer cli list|show|check|install`; parity table; audit event keys in both locales

## 2. Frontend
- [ ] 2.1 `/clis` (problems first) and `/clis/<command>` (Install behind a confirmation naming the Homebrew command, streamed output, login command to copy, Check again)
- [ ] 2.2 Skill detail Requires tab linking each requirement to `/clis/<command>`; sidebar attention signal for CLIs; palette objects

## 3. Tests
- [ ] 3.1 Unit: frontmatter parsing, version comparison, status and ordering, attention items
- [ ] 3.2 Integration: fake probe and installer ports through REST and the CLI; login-check output never kept; install refusal cases
- [ ] 3.3 acceptance(skill-manager, …) and acceptance(resource-framework, …) for every scenario of this change
- [ ] 3.4 Vitest for the pages; e2e for the CLIs page; visual baselines

## 4. Docs
- [ ] 4.1 `docs-site/guides/clis.md`; the skills guide and `writing-skill-libraries.md` document `requires:`; architecture note in `docs-site/architecture/` (skills); skill-manager `data-model.md`; CLI and REST references regenerated

## 5. Verify and archive
- [ ] 5.1 `make verify`, `make verify-e2e`, `make verify-visual`
- [ ] 5.2 Archive the change
