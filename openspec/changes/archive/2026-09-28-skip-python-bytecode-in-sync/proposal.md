## Why

Running a skill's scripts leaves Python bytecode (`__pycache__/*.pyc`) beside them. Sync published it like any other file, so the remote carried caches that change whenever a script runs, and a skill refactor showed up as deletions of `.pyc` files the user never wrote. Separately, `coffer sync now|confirm` printed a round's full per-path change list inline after `published:`, one screen of raw dicts, where it should print counts.

## What Changes

- The skill and knowledge trees are exported without `__pycache__/` directories or `*.pyc`/`*.pyo` files. Bytecode already in the working tree is removed from it by the ordinary differential deletion.
- The CLI round summary (`applied here:` / `published:`, and the `history` line) prints only the counts; the per-path list stays in the round record.

## Capabilities

### New Capabilities

### Modified Capabilities
- `vault-sync`: "Skip symlinks and nested repositories" also leaves Python bytecode out, with one scenario.

## Impact

- Backend: `infrastructure/sync/tree_mirror.py`, `surfaces/cli/sync_cmd.py`.
- Tests: tree mirror, sync CLI.
