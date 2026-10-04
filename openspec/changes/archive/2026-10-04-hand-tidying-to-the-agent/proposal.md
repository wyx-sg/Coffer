## Why

Coffer ran its own model over knowledge and memory: a curation pass folded
inbox material into a collection's documents, and a two-stage distil pass merged
raw memory entries into notes. Both needed a separate model connection the
person had to configure. Without one they fell back to a mechanical path, and on
the maintainer's machine 58 inbox items had waited since 2026-09-28 with
nothing curating them. The judgement these passes made — where a fact belongs,
which notes are the same subject, which statement is stale — is work the
person's own coding agent already does better. It has file tools, a stronger
model and the person watching.

## What Changes

- The `coffer-guide` skill teaches the agent to do that judgement itself. It
  covers writing knowledge straight into a collection's documents by six rules,
  tidying a collection (merge, split, correct), and tidying a memory partition
  (merge notes with their `origins`, retire a note with a `retired:` frontmatter
  key). Its resident description names writing and tidying, so an agent loads
  it when asked to 整理.
- A **Tidy** button on each knowledge collection and each memory partition
  hands the job to the default managed agent. It opens a new conversation with
  the backend's tidy prompt and sends it at once. When no managed agent is
  available, the button offers Copy prompt only.
- The memory distil pass becomes mechanical only. Each new raw entry becomes a
  note as it stands, and the index is rendered. A note carrying `retired:` in its
  frontmatter is recorded in `RETIRED.md` with its origin entry ids and removed.
- Knowledge material is promoted to a document as it stands, at once. An
  upload becomes a document; a file an agent drops into
  `.inbox/` is adopted and promoted by the next sweep. The knowledge sweep keeps
  only its mechanical duties: re-render the guide, adopt and promote dropped
  files, and commit edits found on disk.
- Removed: the curation pass and its route, Curate now, pass undo, the curation
  owner machine, the curate upkeep switch, and the inbox waiting views. Also
  removed: the distil routing and writing stages, the internal default model
  connection (provider `internal_default`, Settings › Coffer's model), and the
  LangChain/LangGraph dependencies.
- Kept: speech-to-text keeps its own connection and model, and the per-call
  model timeout, which moves next to it in Settings. The aggregate and distil
  timers keep their switches and intervals.

## Capabilities

### Modified Capabilities

- `knowledge`: curation requirements removed; material is promoted at once;
  the guide teaches writing and tidying; Tidy hand-off.
- `memory`: distil is mechanical; retirement by a `retired:` frontmatter key;
  Tidy hand-off.
- `internal-engine`: the engine model and the curate pass are removed; the
  settings carry the timeout, the speech-to-text model and the aggregate and
  distil upkeep only.
- `provider-switching`: the internal-default flag and its route are removed.
- `vault-sync`: the unattended rewriter's owner machine and the
  curation/round overlap rule are removed.
- `web-ui`: Settings › Coffer's model is removed; pass undo and waiting items
  leave Knowledge's history and Recent changes.
- `experimental-features`: the knowledge and memory switches gate the sweep and
  the distil pass that remain.
- `resource-framework`: the in-flight passes read names memory's passes only.

## Impact

- Backend: `application/knowledge/` (curation modules deleted, sweep kept),
  `application/memory/` (distil model stages deleted), `application/engine/`,
  `internal_engine_config_service.py`, provider internal-default ops,
  `infrastructure/llm/` (only transcription stays), the HTTP wiring, and
  `pyproject.toml` / `uv.lock` / `coffer-daemon.spec`.
- Wire: the internal-engine, knowledge and provider-switching contracts lose
  routes and fields; collections and partitions gain `tidy_handoff`.
- Frontend: Knowledge, Memory, Settings › General, Model providers and
  Sync › Machines.
- Docs: docs-site knowledge, memory, providers, configuration, filesystem,
  error codes and glossary pages (en + zh); ADRs on curation, the internal
  engine and owner machines.
