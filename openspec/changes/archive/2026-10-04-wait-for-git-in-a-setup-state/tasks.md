## 1. Daemon

- [x] 1.1 `git_requirement.check_git`: daemon `PATH`, then the login shell's; `use_git_dir`
- [x] 1.2 `setup_lifespan.guarded`: setup state instead of the lifespan when no usable git
- [x] 1.3 `setup_state`: status `setup` object, 503 `GIT_NEEDED` guard, `POST /daemon/setup/check`
- [x] 1.4 `/daemon/restart` answers without an audit store; the vault's own version check removed
- [x] 1.5 CLI: commands print the message and hand-off and exit 10; `daemon status` / `start` report it
- [x] 1.6 Shim passes a refusal's message and hand-off on whole
- [x] 1.7 Contract regenerated; error code, i18n fixture

## 2. Web UI

- [x] 2.1 `GitSetupState` screen in the workspace while the status is `setup`
- [x] 2.2 Check again → setup check → host restart

## 3. Tests

- [x] 3.1 Unit: `check_git` ordering, version parsing, `use_git_dir`, setup words
- [x] 3.2 Integration: setup-state lifespan, guard, check again, restart without audit, CLI
- [x] 3.3 Frontend vitest for the screen; acceptance markers for every new scenario

## 4. Docs and canvas

- [x] 4.1 docs-site (en + zh): install requirements, troubleshooting, daemon architecture, error codes, CLI exit codes
- [x] 4.2 README requirements line (en + zh); `install.sh` warns on a missing or old git
- [x] 4.3 Shell canvas board 1.1.22
