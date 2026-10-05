## Why

An agent's Config files tab listed every allowlisted file, including ones the agent had
never written, greyed and marked *Not created*. Those rows could not be opened and Coffer
offers no way to create a config file, so they were noise in a read-only preview.

## What Changes

- The Config files tree lists only the config files and directory entries that exist on
  disk. A file not created yet is left out; the tab shows "No config files found." when none
  exists.
- The listing API is unchanged: it still reports every allowlisted file with its `exists` flag.

## Impact

- Frontend: the Config files tab and its tree.
- Specs: agent-registry. Docs: the Agents guide (en + zh).
