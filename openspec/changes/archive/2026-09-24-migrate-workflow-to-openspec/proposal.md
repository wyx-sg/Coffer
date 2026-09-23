## Why

`main` moved from Speckit to OpenSpec in `adopt-openspec` (#419–#422), and that
change's own design named this branch as the one place still carrying the old
layout. After merging `main`, `feature/workflow` has the workflow spec at
`openspec/specs/workflow/` but still in Speckit form: numbered `FR-` and `SC-`
requirements, a trailing block of scenarios linked to no requirement, a
`plan.md` and a `quickstart.md` kept as if they were permanent, and about 1,100
requirement numbers cited across 200 files. `openspec validate --strict` and
`check_doc_numbering.py` both reject it, and eleven of its requirements have no
scenario and therefore no test.

## What Changes

- Rewrite `openspec/specs/workflow/spec.md` in OpenSpec format by the mapping
  rules of `adopt-openspec`: one `### Requirement:` per former `FR-`, its text
  kept whole; every existing scenario kept by name under the requirement it
  verifies; the principle sections, user stories, success criteria,
  assumptions and out-of-scope list folded into `## Purpose`.
- Give each of the eleven requirements that had no scenario a new scenario, and
  each new scenario a real test carrying an acceptance marker.
- Fold what is still true of `plan.md` and `quickstart.md` into
  `docs/architecture.md`, the workflow ADR and a new `docs-site/guide/`
  page, then delete both files.
- Replace every workflow `FR-` and `SC-` citation in code, tests, the
  contracts, the data model and docs with the requirement's title, checked
  against the requirement's text, and drop the ones that only decorated.
- Regenerate the frontend clients from the edited contracts.

- Hold a template to its own scope on both write paths, and read the
  knowledge catalogue's current fields when a mounted collection is described —
  two places where the code fell short of the spec, found by the new tests.
- Correct the spec text where it disagreed with the index model or the code's
  deliberate choice, and give `web-ui` the two sidebar entries the workflow
  layer adds.

Capabilities whose requirements change:

- `workflow` — changes form; four texts are corrected (a run has no
  conversation of its own, the audit events, two scenario wordings) and a
  disabled workflow now cites the requirement it meant.
- `web-ui` — the sidebar holds thirteen entries: Runs under Agents and
  Workflows under Resources.

## Impact

- Specs: `openspec/specs/workflow/` (spec, data model, contract).
- Docs: `docs/architecture.md`, `docs/decisions/workflow-gates-tool-calls.md`,
  `docs-site/guide/`.
- Code: comments and docstrings in the workflow layer and in the chat,
  gateway, shim and HTTP modules that cite it; the generated workflow and
  mcp-gateway clients; the workflow kind's scope hooks and the knowledge
  input adapter.
- Tests: new acceptance-marked tests for the eleven new scenarios; citation
  comments in existing ones; the web-ui sidebar assertions.
