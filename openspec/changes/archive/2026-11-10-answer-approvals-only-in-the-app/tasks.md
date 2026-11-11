## 1. Command line and daemon

- [x] 1.1 Remove `coffer approval` and its registry rows; exempt the approval routes as the app's own
- [x] 1.2 Report waiting approvals with "answer it in the Coffer app" (CLI exit 9, custom tool error, `SECRET_BINDING_PENDING`, `SECRET_BINDING_REJECTED`)
- [x] 1.3 Drop the `approve` desktop request from the daemon and the shell
- [x] 1.4 List `coffer approval` in `scripts/check_removed_commands.py`

## 2. Guide, specs, docs

- [x] 2.1 coffer-guide: call tools whatever the response holds; leave approvals to the developer
- [x] 2.2 Specs secret and desktop-app edited in place
- [x] 2.3 Docs site (English and Chinese), regenerated CLI reference and coverage, contracts
- [x] 2.4 ADRs
