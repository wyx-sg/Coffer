## Why

Three small web UI adjustments after using the experimental-features build:

- The Settings card says which features are experimental, but the sidebar entries for sync, knowledge and memory look exactly like the finished ones. A user who switched them on — or runs a dev build, where they are on by default — has no cue at the point of use that these surfaces are still being designed.
- The machine registry is something a user returns to (rename this machine, retire one that is gone) long after the remote and key were set, and on Setup it sits below both cards.
- Settings → Security linked to the Sync page for exporting or importing the master key; the Master key card on Sync → Setup is where that happens, and the extra link is noise.

## What Changes

- An experimental feature's sidebar entry carries an "Experimental" / 「实验」 marker beside its label; on a collapsed rail the marker moves into the entry's tooltip, as the label does.
- The Sync page has three tabs: Runs, Setup (remote and master key) and Machines (the registry).
- Settings → Security shows only where the master key is stored.

## Capabilities

### New Capabilities

### Modified Capabilities

- `experimental-features`: a switched-on feature's sidebar entry is marked experimental.
- `vault-sync`: the Sync page gains a Machines tab; Setup holds the remote and the master key.

## Impact

- `frontend/src/components/SidebarNav.tsx`, `frontend/src/pages/sync/SyncPage.tsx`, `SyncSetupTab.tsx`, `frontend/src/pages/settings/SecuritySettings.tsx`, en/zh strings, their tests.
- `docs-site/guides/web-ui.md`, `docs-site/guides/vault-sync.md`.
