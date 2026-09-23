## Context

`feature/workflow` forked from `main` at `317f0607` (#409), before OpenSpec,
and carries two commits: the revert of #410 that restores the workflow layer,
and `d11610f8`, which reshaped it around a per-task deliverable index. The
merge of `origin/main` that precedes this change moved
`specs/workflow/` to `openspec/specs/workflow/` byte for byte and left its
content alone. What it holds:

- `spec.md`: five principle sections, nine user stories, nine edge cases,
  69 requirements `FR-001`…`FR-072` (with gaps), 61 scenarios in a trailing
  `## Acceptance Scenarios` block, six `SC-` success criteria, assumptions and
  an out-of-scope list.
- `data-model.md`, `contracts/api.openapi.yaml`: kept, citing `FR-` numbers.
- `plan.md`, `quickstart.md`: not long-lived files under OpenSpec.

## Decisions

### Spec rewrite

The mapping rules are `adopt-openspec`'s, applied without change:

- Each `FR-` becomes one requirement whose body is the FR's text whole; a
  citation of another FR inside it becomes that requirement's quoted title.
  The bold group headings go.
- Each scenario keeps its name byte for byte and goes under the requirement
  it verifies first. Its `Given/When/Then` become `**GIVEN**/**WHEN**/**THEN**`
  and its trailing `(FR-…)` list goes, since the requirement that owns it now
  says the same thing structurally.
- The principle sections become `## Purpose`. User stories and edge cases add
  nothing a requirement does not already state, except the damage an
  unattended run can do, which joins the gate paragraph. The edge case "a
  run's working directory is deleted while the run is paused" names a
  situation without an outcome and states no behaviour, so it is dropped
  rather than invented. Success criteria become the Purpose's outcomes
  paragraph, as `chat` did; assumptions and the out-of-scope list become its
  last two paragraphs.

The eleven requirements that no scenario verified first each get a new
scenario written from the requirement's own text: stage keys carry no
behaviour; a node names only an agent in scope; the run's working directory is
Coffer's; node statuses; node actions; a retry keeps the earlier attempt;
every input kind is listed and none pasted; unmounting leaves the source
repository alone; a tool call carries its run identity; the audit events; a
run's directory is the only copy of its files.

### Citations

A citation is rewritten by opening the requirement it names and checking the
claim around it against the requirement's text, never by number. The spec
itself had one drift of this kind: disabling a workflow cited `FR-011`
("Create a run from a template and a title alone") for "they froze their own
snapshot", which is `FR-010` ("Freeze the template when a run is created").
Code comments are rewritten to `spec workflow "<Title>"` where the reason
depends on the requirement, and lose the number where it decorated. Only
comments and docstrings change; each Python file is proven unchanged by
comparing its AST with docstrings removed, and each TypeScript file by
comparing its token stream with comments skipped. No automatic re-wrapping is
run over code.

### Plan and quickstart

`plan.md`'s module layout is already in `docs/architecture.md`'s layer tree;
the "composes rather than builds" table, the three changes outside the layer
and the testing approach go to the architecture doc and the ADR where still
true. `quickstart.md` becomes `docs-site/guide/workflows.md`, each command and
path checked against the CLI and the code before it is kept.

### What the new tests found, and what was decided

- **A template's scope was never enforced.** `make_workflow_kind()` was wired
  with no agent set, and the kind's `validate_config` cannot see a resource's
  scope anyway. The kind now takes a reader of the agent rows and supplies
  `on_update_config` and `validate_scope_for`, the two hooks `channel` uses for
  the same inverted scope: a config edit is checked against the scope the row
  has, a scope edit against the config it has. A scope names agents by uid and
  a node by agent key, so the uids are translated through each agent row's
  `type`; a uid no row carries admits nothing, so an unknown agent can only
  narrow a scope. Registration needs no check — a new row has no scope. The
  sync applier writes a converged template through `update_config`, so a
  machine that narrowed a template's scope locally refuses an incoming edit
  naming an agent outside it; that is the rule applied to this machine's own
  scope, and it is the same behaviour a `channel` has.
- **Merging `main` broke the knowledge input.** `main`'s one-tree knowledge
  (#418) renamed `CollectionEntry.source_count`/`topic_count` to
  `document_count`/`pending_count`; the workflow adapter still read the old
  names, so a task with a collection mounted that has no README description
  failed before its turn. The adapter reads the new fields.
- **Spec text corrected, not code.** "Give a run no conversation of its own"
  still said the developer's words reach later tasks as part of the transcript
  they open with, which the index model removed. "Audit template, run, approval
  and gate events" asked for every run state change; the code audits a run's
  start and end on purpose, because pauses and resumes are in the run's own
  event log. Two new scenarios were worded tighter than the requirement: a
  mount creates the run's branch in the source repository and the unmount
  deletes it, and the generated catalogue is a derived file the data model
  asks for.
- **`web-ui` said eleven entries and no twelfth.** It said so while the
  workflow layer was on `main` too; `main`'s tests of it now run here. The
  workflow layer's two surfaces are what the sidebar holds, so `web-ui` is
  updated rather than the entries removed.

## Risks / Trade-offs

- **A new scenario may fail against the code.** Its test is not weakened; the
  discrepancy is decided with the owner, and one that is not fixed here is
  listed in `tasks.md` as a follow-up.
