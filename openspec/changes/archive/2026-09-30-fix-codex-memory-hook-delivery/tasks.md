## 1. Hook commands

- [x] 1.1 `context_invocation` / `hook_command` take the CLI path and an optional hook event; adapters carry `cli`, and the composition root resolves it (`default_coffer_cli_resolver`)
- [x] 1.2 Codex adapter on `SessionStart` with matcher `startup|resume|clear|compact`, `--hook-event SessionStart`, no `$PPID` guard
- [x] 1.3 `coffer memory context --hook-event <Event>` prints `hookSpecificOutput.additionalContext` JSON
- [x] 1.4 `install_entry` / `remove_entry` / `find_installed` sweep every event, so an older build's entry is replaced or removed wherever it sits

## 2. Trust

- [x] 2.1 Kind-agnostic `HookTrust`; Codex adapter computes Codex's hash and reads `[hooks.state]` read only
- [x] 2.2 `DeliveryService.trust` and `HookSite.trust_path`; hooks listing, route, CLI and Hooks tab report `trust`
- [x] 2.3 Reconcile target: `event` and `trust` are parameters; a trust-only difference is a REPORT (`hook_untrusted`, `hook_disabled`, `hook_trust_unknown`) that reaches the attention list

## 3. Delivery size

- [x] 3.1 `compose_context(ceiling_bytes=...)` bounds the whole text in UTF-8 bytes; `POST /memory/context` applies `DELIVERY_CEILING_BYTES` (9,500)

## 4. Tests

- [x] 4.1 Adapter unit tests: event, absolute path, JSON option, migration off `UserPromptSubmit`, Codex hash against values Codex reported, every trust state
- [x] 4.2 Reconcile unit and fake-HOME integration tests: an older build's Codex hook moves to `SessionStart`; an unapproved hook is reported and never written; approval converges the pass
- [x] 4.3 Hooks listing integration and CLI tests for trust; CLI test for `--hook-event`; context tests for the byte ceiling in ASCII and CJK
- [x] 4.4 Frontend: trust chip on the Hooks tab

## 5. Docs

- [x] 5.1 `docs-site/architecture/memory.md`: how delivery reaches each agent, the ceiling, Codex trust
- [x] 5.2 Memory and agents guides, filesystem reference, memory data model, hook-installation ADR
