## 1. Tooling and scaffolding (PR 1)

- [x] 1.1 Add root `package.json` pinning `@fission-ai/openspec` to an exact version, with its lockfile
- [x] 1.2 Run `openspec init --tools claude`; commit `openspec/`, `.claude/commands/opsx/` and `.claude/skills/openspec-*`; un-ignore `.claude/commands/opsx/` in `.gitignore`
- [x] 1.3 Write `openspec/config.yaml`: `context:` from the constitution's technology constraints and the stack, `rules:` for specs, design and tasks from the constitution and `.agents/sdd.md`
- [x] 1.4 Add `make openspec-validate` and call it from `make verify`; add the same step to `.github/workflows/verify.yml`
- [x] 1.5 Teach `audit_acceptance.py` to read scenarios from both `specs/` (old) and `openspec/specs/` (new), and to reject duplicate scenario names within a spec
- [x] 1.6 Move `.specify/memory/architecture.md` to `docs/architecture.md`; point `check_architecture_doc.py` at it
- [x] 1.7 Turn `.specify/memory/constitution.md` into `docs/principles.md`; point every reference at it
- [x] 1.8 Delete `.specify/memory/roadmap.md` and `.specify/templates/`
- [x] 1.9 Replace `.agents/sdd.md` with `.agents/openspec.md`; update every inbound link
- [x] 1.10 Delete `.claude/skills/coffer-spec/`; update `.agents/harness.md`
- [x] 1.11 Rewrite the Speckit passages in `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`, `.agents/stack.md`, `.agents/testing.md`, `docs-site/contributing/index.md`, `docs-site/architecture/principles.md`, the nine ADRs and `docs/research/*` that mention it
- [ ] 1.12 Run `make verify`; open PR 1

## 2. Spec rewrite and new tests (PR 2)

- [ ] 2.1 `git mv specs openspec/specs`; update the contract tests, `frontend/scripts/codegen{,-check}.mjs`, generated clients, schema modules and `frontend/src/test/acceptance.ts` that name `specs/`; re-run codegen
- [ ] 2.2 Rewrite `resource-framework/spec.md` into OpenSpec format; record its FR→title map in the scratchpad
- [ ] 2.3 Rewrite `mcp-gateway/spec.md`
- [ ] 2.4 Rewrite `agent-registry/spec.md`, `agent-registry/claude-code/spec.md`, `agent-registry/codex/spec.md`
- [ ] 2.5 Rewrite `channels/spec.md`, `channels/telegram/spec.md`, `channels/seatalk/spec.md`
- [ ] 2.6 Rewrite `chat/spec.md`
- [ ] 2.7 Rewrite `credentials/spec.md`
- [ ] 2.8 Rewrite `daemon/spec.md`
- [ ] 2.9 Rewrite `desktop-app/spec.md`
- [ ] 2.10 Rewrite `internal-engine/spec.md`
- [ ] 2.11 Rewrite `knowledge/spec.md`
- [ ] 2.12 Rewrite `memory/spec.md`
- [ ] 2.13 Rewrite `provider-switching/spec.md`
- [ ] 2.14 Rewrite `skill-manager/spec.md`
- [ ] 2.15 Rewrite `vault-sync/spec.md`
- [ ] 2.16 Rewrite `web-ui/spec.md`
- [ ] 2.17 For every capability, check that each old scenario appears exactly once and each requirement owns at least one scenario
- [ ] 2.18 Fold each `plan.md` and `research.md` into `docs/architecture.md` or an ADR, then delete them
- [ ] 2.19 Merge each `quickstart.md` into its `docs-site/guide/` page, then delete them
- [ ] 2.20 Write an acceptance-marked test for every scenario added in 2.2–2.16; list any that exposes a real defect under section 4
- [ ] 2.21 Repoint or drop every link inside `openspec/specs/` to a file phase 1 removed (`.specify/…`, `.agents/sdd.md`)
- [ ] 2.22 Run `openspec validate --all --strict` and `make verify`; open PR 2

## 3. Requirement numbers out (PR 3)

- [ ] 3.1 Rewrite every `FR-<n>` citation in `backend/coffer`, `backend/tests`, `frontend/src`, `desktop/src` and `e2e` to the requirement title, or drop it where it only decorated the comment
- [ ] 3.2 Rewrite every `FR-<n>` citation in `docs/decisions`, `docs/research`, `docs-site` and `.agents` as a spec link plus requirement title
- [ ] 3.3 `check_doc_numbering.py`: drop the unique-FR rule, reject any `FR-<n>` token; delete `docs/decisions/fr-ids-reset-once.md` and its index entry
- [ ] 3.4 Add the check that fails on `.specify/`, a root `specs/`, or `speckit`/`spec-kit` in any tracked file
- [ ] 3.5 Remove the old-layout path from `audit_acceptance.py`
- [ ] 3.6 Run `make verify`; open PR 3

## 4. Follow-ups found during the migration

- [ ] 4.1 (none yet)

## 5. Close

- [ ] 5.1 `openspec archive adopt-openspec`
