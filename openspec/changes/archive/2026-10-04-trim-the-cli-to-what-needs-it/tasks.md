## 1. CLI

- [x] 1.1 The reasoned command list (design §1) in one CLI module, and a test asserting the live tree equals it with a reason per row; delete the parity test
- [x] 1.2 Delete every command not on the list, its module or registration, and its CLI tests; `memory hook` and `proxy token` hidden
- [x] 1.3 `coffer config` keys narrowed to the pre-bind daemon settings
- [x] 1.4 `scripts/check_removed_commands.py` lists every removed spelling with where the operation lives now

## 2. Prompts, hints and copy

- [x] 2.1 Hand-off prompts, the `coffer-guide` manual, gateway instructions, error hints and log/CLI messages name only kept commands or the web UI step
- [x] 2.2 Web UI copy (offline banner, daemon status card, secret refs, channel dir switch) names only kept commands

## 3. Specs, policy and docs

- [x] 3.1 Deltas for every capability that names a removed command; resource-framework's parity requirement becomes "Keep the command line to what needs it"
- [x] 3.2 `.agents/openspec.md` "End-to-End Deliverable Rule" states the minimal-CLI rule
- [x] 3.3 Regenerate the CLI reference; every docs-site page (en + zh) and README that shows a removed command shows the web UI step

## 4. Verify

- [x] 4.1 `npx openspec validate --all --strict`, `make lint`, `make verify`
- [x] 4.2 Archive the change
