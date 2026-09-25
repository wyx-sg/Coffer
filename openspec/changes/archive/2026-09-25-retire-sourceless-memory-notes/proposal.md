## Why

Since placement files a `feedback` entry that carries a project root into that project's partition (and `.source_state.json` moved to version 2 so the next aggregation re-files existing raw entries), the raw entries move — but the notes distil had already written into `global` stay. Distil never removes a note whose supporting raw entries have all disappeared, so the same lesson is served from both `global` and the project partition, and a fact an agent deleted from its own memory lives on in Coffer's notes indefinitely.

## What Changes

- Every distil pass, model-driven or mechanical, first retires each note none of whose provenance entries is still under the partition's `.raw/`, deleting its file and recording it in `RETIRED.md` with a reason saying its sources are gone.
- Such a record carries `sources_gone: true` and no `entry_ids`, and its title is not handed to routing as an excluded subject — nothing judged the note untrue, so material that returns is distilled afresh.
- The pass's `retired` count includes these retirements.

## Capabilities

### New Capabilities

### Modified Capabilities
- `memory`: adds "Retire a note whose raw entries are all gone"; "Distil mechanically with no internal connection" states that the mechanical path performs that retirement too.

## Impact

- `backend/coffer/application/memory/distil.py`, `distil_plan.py`; `domain/memory/retired.py`; `infrastructure/memory/store.py` (`RETIRED.md` gains an optional `sources_gone` field).
- No route, CLI or schema change; `DistilResultOut.retired`'s description widens.
- Docs: `openspec/specs/memory/data-model.md`, the memory guide and architecture page in `docs-site/`.
