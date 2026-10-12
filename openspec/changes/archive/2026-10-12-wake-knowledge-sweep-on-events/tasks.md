## 1. Wake the sweep

- [x] 1.1 `VaultScanner.on_subtree_event` lets a worker borrow the vault's file watch for one subtree
- [x] 1.2 The knowledge sweep runs on a `WakeableLoop` poked by `knowledge/` events and the feature switch, with a 10-minute fallback and a 1 s settle
- [x] 1.3 A loose document inside its quiet minute schedules one more run
- [x] 1.4 The lifespan hands the scanner's hook to the background-worker launcher

## 2. Tests and docs

- [x] 2.1 A knowledge file event wakes the sweep, a burst is one run, and the sweep is listed on `runtime.workers`
- [x] 2.2 The scanner calls a subtree listener only for events under that subtree
- [x] 2.3 daemon architecture page (en and zh), the ADR, and the knowledge spec and data model say event-driven
