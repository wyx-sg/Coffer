## 1. Merge

- [x] 1.1 Merge `origin/main` into `feature/workflow`; resolve conflicts in favour of `main`'s layout; move `specs/workflow/` to `openspec/specs/workflow/`; renumber the branch's migration 0101 → 0103

## 2. Spec

- [x] 2.1 Rewrite `openspec/specs/workflow/spec.md` into OpenSpec format; record the FR→title map in the scratchpad
- [x] 2.2 Check that each old scenario appears exactly once and each requirement owns at least one scenario
- [x] 2.3 Write an acceptance-marked test for each of the eleven new scenarios
- [x] 2.4 Replace the `FR-` citations in `data-model.md` and `contracts/api.openapi.yaml`; re-run frontend codegen

## 3. Plan and quickstart

- [x] 3.1 Fold what is still true of `plan.md` into `docs/architecture.md` and the workflow ADR; delete it
- [x] 3.2 Turn `quickstart.md` into `docs-site/guide/workflows.md`, checked against the CLI; delete it
- [x] 3.3 Repoint every link to either file

## 4. Requirement numbers out

- [x] 4.1 `backend/coffer`: rewrite each workflow `FR-` citation to its title after checking it; prove comment-only by AST
- [x] 4.2 `backend/tests`: the same
- [x] 4.3 `frontend/src` and `e2e`: the same; prove comment-only by token stream
- [x] 4.4 `openspec/specs/mcp-gateway/` and docs: the same

## 5. What the new tests found

- [x] 5.1 Hold a template to its scope on config and scope edits (`on_update_config`, `validate_scope_for`), translating scope uids to agent keys
- [x] 5.2 Read `document_count`/`pending_count` in the knowledge input adapter (broken by the merge of #418)
- [x] 5.3 Correct the workflow spec text: a run's words reach later tasks by the deliverable; the audit events are a run's start and end; the two new scenario wordings
- [x] 5.4 Give `web-ui` the Runs and Workflows sidebar entries; update its sidebar and one-name tests

## 6. Follow-ups found during the migration

Each is a place the code or its prose falls short of the spec, left for its own change:

- [ ] 6.1 `coffer workflow approve` cannot remember a tool's write-class judgement; only the web UI sends `remember_tool_class` ("Treat an unjudged tool as write-class and remember the answer", and REST/CLI parity)
- [ ] 6.2 The web UI cannot start, pause, resume or abort a run, nor complete or skip a task waiting for review; both need the CLI
- [ ] 6.3 `promote_artifacts` says it adds to an existing collection, but creating the collection raises `CollectionExists` when it is there; no test covers it
- [ ] 6.4 Stale prose: `frontend/src/lib/api/queryKeys.ts` names an approvals page that is not routed; `test_approval_service.py` says an approval reaches "the main thread"

## 7. Close

- [x] 7.1 `make lint`, `make verify-acceptance`, backend unit, contract and integration, frontend vitest and typecheck, `npm run codegen:check`
- [x] 7.2 `openspec archive migrate-workflow-to-openspec --yes`
