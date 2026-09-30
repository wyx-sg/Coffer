## 1. Capability

- [x] 1.1 Move `openspec/specs/credentials/` to `openspec/specs/secret/` and retitle the spec "Secrets"
- [x] 1.2 Assign the `/api/v1/credentials` and `/api/v1/settings` routes to `secret` in `scripts/gen_contracts.py` and regenerate the contract
- [x] 1.3 Rewrite every citation, spec link and acceptance marker that names `credentials` as a capability

## 2. Command line

- [x] 2.1 Replace the `coffer credentials` group with `coffer secret` (same subcommands, no alias)
- [x] 2.2 Say "secret" in the group's help, output and error text
- [x] 2.3 Add `coffer credentials` to `scripts/check_removed_commands.py` with `coffer secret` as the replacement
- [x] 2.4 Update CLI tests

## 3. Words users read

- [x] 3.1 Web UI strings (en, zh): "secret" wherever a user reads "credential"
- [x] 3.2 docs-site, README, `.agents/`, the coffer-guide skill; regenerate the CLI reference (`make docs-reference`)
- [x] 3.3 e2e specs that run or quote the command
