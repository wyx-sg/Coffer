## Why

The Add-skill dialog's path field was read-only: the only way in was Browse.
A user who already has the skill's path at hand — copied from a terminal, a
file manager or a chat — had to click through a folder dialog to reach it.

## What Changes

- The Add-skill dialog's path field accepts a typed or pasted path beside the
  Browse button. Surrounding whitespace and quotes are stripped before import,
  and `~` is expanded by the daemon as it already is for the CLI.
- The shared picker row (`PickerField` / `FolderPickerField`) gains an opt-in
  editable mode; the agent config-directory picker stays pick-only.

## Capabilities

### New Capabilities

### Modified Capabilities

- `skill-manager`

## Impact

`frontend/src/components/PickerField.tsx`, `FolderPickerField.tsx`,
`skills/SkillAddDialog.tsx` and its test; the skills guide.
