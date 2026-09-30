## 1. Specs and data models

- [x] 1.1 Rename the internal-engine and daemon requirements and move every citation
- [x] 1.2 Correct the storage wording in secret, internal-engine, vault-sync, memory, knowledge, channels and web-ui, with the scenario renames and their markers
- [x] 1.3 Add the vault-storage requirements for recent changes, refused hand edits and the git minimum, with markers on tests
- [x] 1.4 Add the channel detail tabs to channels, with a marker on the page test
- [x] 1.5 Fix the data models (mcp-gateway, secret, channels, memory, knowledge, vault-storage, internal-engine) and regenerate the memory contract

## 2. Code

- [x] 2.1 Hand a too-old git to an agent (`domain/git_handoff.py`) and drop the installer from the refusal
- [x] 2.2 Replace the desktop app's install command with the install page and an agent prompt
- [x] 2.3 Serve the API schema behind the token and switch off `/docs` and `/redoc`
- [x] 2.4 Add `--username` to `coffer sync remote check`; regenerate the CLI reference and fix the GitLab example
- [x] 2.5 Correct the stale comments and docstrings the audit found

## 3. Gates

- [x] 3.1 Read relative spec links and `see "<Title>"` in `check_spec_citations.py`, and fix what it then finds
- [x] 3.2 Scan `README.zh-CN.md`, `docs/` (not the ADRs) and `desktop/src` in `check_removed_commands.py`
- [x] 3.3 Add `check_error_codes_reference.py` to `make lint` and bring both error-code pages up to date
