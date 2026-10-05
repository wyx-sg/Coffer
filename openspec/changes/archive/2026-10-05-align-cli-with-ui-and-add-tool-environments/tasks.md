## 1. Custom-tool environments and argument validation

- [x] 1.1 Domain: `HttpApiEnvironment`, legacy lift to `default`, `select_environment`, the reserved `coffer_environment` argument and the advertised schema; `{env:NAME}` variables, refused in a base URL; tests
- [x] 1.2 Domain: one JSON Schema validator (types, enum, ranges, array limits, combinators, `additionalProperties`) and a schema check on save; per-field errors; tests
- [x] 1.3 Application: environments added, renamed, switched off and deleted (the last one refused); saved-tool and draft tests in a chosen environment; re-import keeps environments; tests
- [x] 1.4 Secrets: a destination per environment (`<group> · <env>`), secrets resolved only for the chosen environment, a target change re-pends only that environment; tests
- [x] 1.5 Gateway and runner: per-call environment, refused before any request when invalid, off or unapproved; invocation rows carry the environment (migration 0151); concurrency test
- [x] 1.6 REST: environment routes, saved-tool test route, test answers name the environment and the URL reached; contracts regenerated

## 2. Command line

- [x] 2.1 Shared contract: `--json`, `--data` (text, `@file`, `-`), `--set`, error envelope, exit codes 0–13
- [x] 2.2 Declarative `RouteCommand` builder and the registry (`OPERATIONS`, `EXEMPT`, `SHELL_COMMANDS`)
- [x] 2.3 `coffer custom-tool` over every Custom tools route, OpenAPI import and re-import preview/apply; CLI create → read back test
- [x] 2.4 A command for every other route the web UI calls and every desktop command; coverage check (`scripts/cli_coverage.py`) with zero gaps, in `make lint`
- [x] 2.5 Parity tests: every declared command against a recording transport, every leaf recorded or reasoned, every group's `--help`
- [x] 2.6 The removed-commands gate keeps only spellings still gone

## 3. Approvals and presence from the command line

- [x] 3.1 Daemon desktop-request queue (status, requests, claim, finish, cancel) with a TTL and heartbeat
- [x] 3.2 Grants pinned to the approval's target fingerprint; a changed target approves nothing
- [x] 3.3 `coffer approval list|show|approve|reject`, `coffer secret reveal`, `coffer secret backup-key`, `coffer app update`; the app is launched or the command exits 12; tests with a fake shell
- [x] 3.4 Desktop shell: request watcher, pinned single and batch approve, reveal shown only in the app; Rust tests and clippy

## 4. Web UI

- [x] 4.1 Environments section, environment dialog with variables, test-panel environment picker, "Ran in", per-environment log column; en/zh copy; component tests
- [x] 4.2 Design canvas boards for the Custom tools page

## 5. Docs

- [x] 5.1 ADR `command-line-parity-with-the-web-ui`; `.agents/openspec.md` policy paragraph
- [x] 5.2 CLI reference and coverage pages (en/zh), guides, architecture pages and error codes
